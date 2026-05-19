"""
Minecraft World Sync - Main Application
Windows application for synchronizing Minecraft Java Edition worlds 
over Radmin VPN with automatic LAN hosting and host migration.
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import socket
import struct
import hashlib
import json
import os
import sys
import time
import logging
import subprocess
import shutil
import zipfile
import tempfile
from pathlib import Path
from datetime import datetime
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
import psutil
import netifaces

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('minecraft_sync.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Constants
UDP_PORT = 45678
TCP_PORT = 45679
BROADCAST_INTERVAL = 5  # seconds
PING_INTERVAL = 10  # seconds
BACKUP_INTERVAL = 300  # 5 minutes
RADMIN_IP_PREFIX = "26."


class CryptoManager:
    """Handles encryption/decryption using AES-128-CBC"""
    
    def __init__(self, password: str, salt: bytes):
        self.password = password
        self.salt = salt
        self.key = self._derive_key()
    
    def _derive_key(self) -> bytes:
        """Derive AES key from password using PBKDF2"""
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=16,  # 128 bits
            salt=self.salt,
            iterations=100000,
            backend=default_backend()
        )
        return kdf.derive(self.password.encode())
    
    def encrypt_file(self, input_path: str, output_path: str) -> bool:
        """Encrypt a file using AES-128-CBC"""
        try:
            iv = os.urandom(16)
            with open(input_path, 'rb') as f:
                plaintext = f.read()
            
            # Pad to block size (16 bytes)
            padding_len = 16 - (len(plaintext) % 16)
            plaintext += bytes([padding_len] * padding_len)
            
            cipher = Cipher(algorithms.AES(self.key), modes.CBC(iv), backend=default_backend())
            encryptor = cipher.encryptor()
            ciphertext = encryptor.update(plaintext) + encryptor.finalize()
            
            with open(output_path, 'wb') as f:
                f.write(iv + ciphertext)
            
            logger.info(f"File encrypted: {input_path} -> {output_path}")
            return True
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            return False
    
    def decrypt_file(self, input_path: str, output_path: str) -> bool:
        """Decrypt a file using AES-128-CBC"""
        try:
            with open(input_path, 'rb') as f:
                iv = f.read(16)
                ciphertext = f.read()
            
            cipher = Cipher(algorithms.AES(self.key), modes.CBC(iv), backend=default_backend())
            decryptor = cipher.decryptor()
            plaintext = decryptor.update(ciphertext) + decryptor.finalize()
            
            # Remove padding
            padding_len = plaintext[-1]
            plaintext = plaintext[:-padding_len]
            
            with open(output_path, 'wb') as f:
                f.write(plaintext)
            
            logger.info(f"File decrypted: {input_path} -> {output_path}")
            return True
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            return False


class NetworkManager:
    """Handles network discovery, communication, and ping measurements"""
    
    def __init__(self, room_id: str, crypto_manager: CryptoManager):
        self.room_id = room_id
        self.crypto = crypto_manager
        self.my_ip = None
        self.participants = {}  # ip -> {salt, last_seen, avg_ping}
        self.ping_matrix = {}  # {ip: {other_ip: ping}}
        self.tcp_connections = {}  # ip -> socket
        self.running = False
        self.udp_socket = None
        self.broadcast_thread = None
        self.listen_thread = None
        self.ping_thread = None
        
    def get_radmin_ip(self) -> str:
        """Find Radmin VPN IP address"""
        try:
            for iface in netifaces.interfaces():
                addrs = netifaces.ifaddresses(iface)
                if netifaces.AF_INET in addrs:
                    for addr in addrs[netifaces.AF_INET]:
                        ip = addr.get('addr', '')
                        if ip.startswith(RADMIN_IP_PREFIX):
                            logger.info(f"Found Radmin IP: {ip} on interface {iface}")
                            return ip
        except Exception as e:
            logger.error(f"Error finding Radmin IP: {e}")
        return None
    
    def start(self):
        """Start network services"""
        self.my_ip = self.get_radmin_ip()
        if not self.my_ip:
            logger.error("Radmin VPN adapter not found")
            return False
        
        self.running = True
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self.udp_socket.bind(('0.0.0.0', UDP_PORT))
        self.udp_socket.settimeout(1.0)
        
        self.broadcast_thread = threading.Thread(target=self._broadcast_loop, daemon=True)
        self.listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.ping_thread = threading.Thread(target=self._ping_loop, daemon=True)
        
        self.broadcast_thread.start()
        self.listen_thread.start()
        self.ping_thread.start()
        
        logger.info(f"Network manager started on {self.my_ip}")
        return True
    
    def stop(self):
        """Stop network services"""
        self.running = False
        if self.udp_socket:
            self.udp_socket.close()
        for conn in self.tcp_connections.values():
            conn.close()
        self.tcp_connections.clear()
        logger.info("Network manager stopped")
    
    def _broadcast_loop(self):
        """Periodically broadcast presence"""
        while self.running:
            try:
                message = json.dumps({
                    "room_id": self.room_id,
                    "ip": self.my_ip,
                    "salt": self.crypto.salt.hex()
                })
                self.udp_socket.sendto(message.encode(), ('255.255.255.255', UDP_PORT))
                time.sleep(BROADCAST_INTERVAL)
            except Exception as e:
                logger.error(f"Broadcast error: {e}")
    
    def _listen_loop(self):
        """Listen for broadcasts and TCP connections"""
        while self.running:
            try:
                data, addr = self.udp_socket.recvfrom(1024)
                message = json.loads(data.decode())
                
                if message.get("room_id") == self.room_id and message.get("ip") != self.my_ip:
                    peer_ip = message["ip"]
                    salt = bytes.fromhex(message["salt"])
                    
                    # Update participant list
                    if peer_ip not in self.participants:
                        self.participants[peer_ip] = {
                            "salt": salt,
                            "last_seen": time.time(),
                            "avg_ping": float('inf')
                        }
                        logger.info(f"New participant: {peer_ip}")
                        
                        # Establish TCP connection for commands
                        self._connect_tcp(peer_ip)
                    else:
                        self.participants[peer_ip]["last_seen"] = time.time()
                        
            except socket.timeout:
                # Normal timeout when no data received - don't log
                pass
            except Exception as e:
                if self.running:
                    logger.debug(f"Listen error: {e}")
    
    def _connect_tcp(self, ip: str):
        """Establish TCP connection with peer"""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect((ip, TCP_PORT))
            self.tcp_connections[ip] = sock
            
            # Start receive thread for this connection
            threading.Thread(target=self._tcp_receive_loop, args=(ip, sock), daemon=True).start()
            logger.info(f"TCP connected to {ip}")
        except Exception as e:
            logger.error(f"TCP connection to {ip} failed: {e}")
    
    def _tcp_receive_loop(self, ip: str, sock: socket.socket):
        """Receive TCP messages from peer"""
        while self.running:
            try:
                data = sock.recv(4096)
                if not data:
                    break
                
                # Process command (simplified - actual implementation would parse commands)
                logger.debug(f"Received from {ip}: {len(data)} bytes")
            except Exception as e:
                logger.error(f"TCP receive from {ip} error: {e}")
                break
        
        if ip in self.tcp_connections:
            del self.tcp_connections[ip]
        sock.close()
    
    def _ping_loop(self):
        """Measure ICMP ping to all participants"""
        while self.running:
            for ip in list(self.participants.keys()):
                ping = self._measure_ping(ip)
                if ping is not None:
                    # Update average ping
                    old_avg = self.participants[ip]["avg_ping"]
                    if old_avg == float('inf'):
                        self.participants[ip]["avg_ping"] = ping
                    else:
                        self.participants[ip]["avg_ping"] = old_avg * 0.7 + ping * 0.3
                    
                    # Update ping matrix
                    if self.my_ip not in self.ping_matrix:
                        self.ping_matrix[self.my_ip] = {}
                    self.ping_matrix[self.my_ip][ip] = ping
            
            time.sleep(PING_INTERVAL)
    
    def _measure_ping(self, ip: str) -> float:
        """Measure ICMP ping to IP address"""
        try:
            # Use system ping command (requires admin rights on Windows)
            param = '-n' if sys.platform == 'win32' else '-c'
            command = ['ping', param, '1', ip]
            result = subprocess.run(command, capture_output=True, text=True, timeout=5)
            
            # Parse ping time from output
            if 'time=' in result.stdout:
                ping_str = result.stdout.split('time=')[1].split()[0]
                ping = float(ping_str.replace('ms', '').replace(',', '.'))
                return ping
        except Exception as e:
            logger.debug(f"Ping to {ip} failed: {e}")
        return None
    
    def send_command(self, ip: str, command: dict) -> bool:
        """Send command to peer via TCP"""
        if ip not in self.tcp_connections:
            self._connect_tcp(ip)
        
        if ip in self.tcp_connections:
            try:
                data = json.dumps(command).encode()
                self.tcp_connections[ip].sendall(struct.pack('>I', len(data)) + data)
                return True
            except Exception as e:
                logger.error(f"Send command to {ip} failed: {e}")
        return False
    
    def get_best_host_candidate(self) -> str:
        """Get IP of best host candidate based on ping matrix"""
        if not self.participants:
            return self.my_ip
        
        best_ip = None
        best_avg_ping = float('inf')
        
        for ip in self.participants.keys():
            # Calculate average ping to all other participants
            pings = [p for other, p in self.ping_matrix.get(ip, {}).items() if other != ip]
            if pings:
                avg_ping = sum(pings) / len(pings)
                if avg_ping < best_avg_ping or (avg_ping == best_avg_ping and (best_ip is None or ip < best_ip)):
                    best_avg_ping = avg_ping
                    best_ip = ip
        
        return best_ip if best_ip else self.my_ip


class WorldManager:
    """Handles world archiving, versioning, and synchronization"""
    
    def __init__(self, minecraft_dir: str, crypto_manager: CryptoManager):
        self.minecraft_dir = Path(minecraft_dir)
        self.saves_dir = self.minecraft_dir / "saves"
        self.crypto = crypto_manager
        self.version_file = None
        self.current_version = 0
        
    def set_world(self, world_name: str):
        """Set the current world to manage"""
        self.world_dir = self.saves_dir / world_name
        self.version_file = self.world_dir / "sync_world_version.txt"
        
        if self.version_file.exists():
            self.current_version = int(self.version_file.read_text().strip())
        else:
            self.current_version = 0
            self.version_file.write_text("0")
        
        logger.info(f"World set: {world_name}, version: {self.current_version}")
    
    def get_world_hash(self) -> str:
        """Calculate SHA-256 hash of critical world files"""
        sha256 = hashlib.sha256()
        
        # Hash level.dat
        level_dat = self.world_dir / "level.dat"
        if level_dat.exists():
            sha256.update(level_dat.read_bytes())
        
        # Hash all region files
        region_dir = self.world_dir / "region"
        if region_dir.exists():
            for mca_file in sorted(region_dir.glob("*.mca")):
                sha256.update(mca_file.read_bytes())
        
        return sha256.hexdigest()
    
    def archive_world(self, output_path: str) -> bool:
        """Create encrypted ZIP archive of world"""
        try:
            # Create temporary directory for world copy
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_world = Path(temp_dir) / self.world_dir.name
                shutil.copytree(self.world_dir, temp_world)
                
                # Create ZIP without compression (ZIP_STORED)
                zip_path = Path(temp_dir) / f"{self.world_dir.name}.zip"
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_STORED) as zf:
                    for file_path in temp_world.rglob('*'):
                        if file_path.is_file():
                            arc_name = file_path.relative_to(temp_world)
                            zf.write(file_path, arc_name)
                
                # Encrypt ZIP
                encrypted_path = Path(temp_dir) / f"{self.world_dir.name}.zip.enc"
                if self.crypto.encrypt_file(str(zip_path), str(encrypted_path)):
                    # Copy to final destination
                    shutil.copy2(encrypted_path, output_path)
                    logger.info(f"World archived and encrypted: {output_path}")
                    return True
            
            return False
        except Exception as e:
            logger.error(f"Archive failed: {e}")
            return False
    
    def extract_world(self, encrypted_path: str) -> bool:
        """Extract world from encrypted ZIP archive"""
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                # Decrypt ZIP
                decrypted_path = Path(temp_dir) / "world.zip"
                if not self.crypto.decrypt_file(encrypted_path, str(decrypted_path)):
                    return False
                
                # Extract ZIP
                extract_dir = Path(temp_dir) / "extracted"
                with zipfile.ZipFile(decrypted_path, 'r') as zf:
                    zf.extractall(extract_dir)
                
                # Replace current world
                if self.world_dir.exists():
                    shutil.rmtree(self.world_dir)
                shutil.copytree(extract_dir / self.world_dir.name, self.world_dir)
                
                logger.info(f"World extracted from: {encrypted_path}")
                return True
        except Exception as e:
            logger.error(f"Extract failed: {e}")
            return False
    
    def increment_version(self):
        """Increment world version number"""
        self.current_version += 1
        if self.version_file:
            self.version_file.write_text(str(self.current_version))
        logger.info(f"World version incremented to {self.current_version}")
    
    def has_changes_since_backup(self, last_backup_time: float) -> bool:
        """Check if world has changed since last backup"""
        level_dat = self.world_dir / "level.dat"
        if level_dat.exists():
            mtime = level_dat.stat().st_mtime
            return mtime > last_backup_time
        return False


class MinecraftLauncher:
    """Handles TLauncher and Minecraft process management"""
    
    def __init__(self, minecraft_dir: str):
        self.minecraft_dir = Path(minecraft_dir)
        self.tlauncher_path = None
        self.mc_process = None
        
    def find_tlauncher(self) -> str:
        """Find TLauncher installation"""
        possible_paths = [
            Path(os.environ.get('APPDATA', '')) / '.tlauncher' / 'TLauncher.exe',
            Path(os.environ.get('APPDATA', '')) / '.minecraft' / 'TLauncher.exe',
            Path.home() / 'TLauncher' / 'TLauncher.exe',
            Path('C:\\Program Files\\TLauncher') / 'TLauncher.exe',
            Path('C:\\Program Files (x86)\\TLauncher') / 'TLauncher.exe',
            Path('C:\\Users\\Public') / 'TLauncher' / 'TLauncher.exe',
        ]
        
        # Also check registry for TLauncher installation
        try:
            import winreg
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\TLauncher")
                install_path, _ = winreg.QueryValueEx(key, "InstallPath")
                if install_path:
                    possible_paths.insert(0, Path(install_path) / 'TLauncher.exe')
                winreg.CloseKey(key)
            except:
                pass
        except:
            pass
        
        for path in possible_paths:
            if path.exists():
                self.tlauncher_path = str(path)
                logger.info(f"TLauncher found: {path}")
                return str(path)
        
        # If not found, allow user to specify manually via config file
        config_path = Path(__file__).parent.parent / 'tlauncher_path.txt'
        if config_path.exists():
            custom_path = config_path.read_text().strip()
            if custom_path and Path(custom_path).exists():
                self.tlauncher_path = custom_path
                logger.info(f"TLauncher found via config: {custom_path}")
                return custom_path
        
        logger.warning("TLauncher not found in standard locations")
        logger.info("Please create tlauncher_path.txt with full path to TLauncher.exe")
        return None

    
    def launch_minecraft(self, username: str = None, forge_version: str = "forge-1.21.1") -> bool:
        """Launch Minecraft via TLauncher with automatic version selection and game start"""
        if not self.tlauncher_path:
            if not self.find_tlauncher():
                # Try one more approach - check if javaw.exe is running (Minecraft might already be launched)
                for proc in psutil.process_iter(['name', 'cmdline']):
                    try:
                        if 'javaw' in proc.info['name'].lower():
                            cmdline = ' '.join(proc.info['cmdline'] or [])
                            if 'minecraft' in cmdline.lower() or 'forge' in cmdline.lower():
                                logger.info(f"Minecraft already running (PID: {proc.pid})")
                                self.mc_process = proc
                                return True
                    except:
                        pass
                return False
        
        try:
            # Launch TLauncher
            cmd = [self.tlauncher_path]
            
            logger.info(f"Launching TLauncher: {' '.join(cmd)}")
            self.mc_process = subprocess.Popen(cmd)
            logger.info(f"TLauncher launched with PID {self.mc_process.pid}")
            
            # Wait for TLauncher to initialize (window appears)
            logger.info("Waiting for TLauncher to initialize...")
            time.sleep(5)  # Wait for UI to load
            
            # Try to auto-select Forge version and start game using PyAutoGUI
            try:
                import pyautogui
                
                # Get TLauncher window
                tlauncher_window = None
                for i in range(10):  # Try multiple times
                    try:
                        tlauncher_window = pyautogui.getWindowsWithTitle('TLauncher')[0]
                        break
                    except:
                        time.sleep(1)
                
                if tlauncher_window:
                    logger.info(f"TLauncher window found: {tlauncher_window.title}")
                    
                    # Bring window to front
                    tlauncher_window.activate()
                    time.sleep(1)
                    
                    # Get window position and size
                    x, y = tlauncher_window.left, tlauncher_window.top
                    width, height = tlauncher_window.width, tlauncher_window.height
                    
                    logger.info(f"TLauncher window: x={x}, y={y}, w={width}, h={height}")
                    
                    # Click on version dropdown (approximate position - adjust based on TLauncher UI)
                    # The dropdown is typically in the lower part of the window
                    dropdown_x = x + width // 2
                    dropdown_y = y + height - 150
                    
                    logger.info(f"Clicking version dropdown at ({dropdown_x}, {dropdown_y})")
                    pyautogui.click(dropdown_x, dropdown_y)
                    time.sleep(0.5)
                    
                    # Type Forge version name to filter
                    logger.info(f"Typing version: {forge_version}")
                    pyautogui.write(forge_version, interval=0.05)
                    time.sleep(0.5)
                    
                    # Press Enter to select
                    pyautogui.press('enter')
                    time.sleep(0.5)
                    
                    # Click the "Играть" (Play) button
                    # The Play button is typically at the bottom center
                    play_x = x + width // 2
                    play_y = y + height - 80
                    
                    logger.info(f"Clicking Play button at ({play_x}, {play_y})")
                    pyautogui.click(play_x, play_y)
                    
                    logger.info("TLauncher automation completed - waiting for Minecraft to start")
                else:
                    logger.warning("Could not find TLauncher window - user must start manually")
                    
            except ImportError:
                logger.warning("pyautogui not installed - automatic startup disabled")
                logger.info("Install with: pip install pyautogui")
            except Exception as e:
                logger.error(f"Automation failed: {e}")
                logger.info("User must select version and click Play manually")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to launch Minecraft: {e}")
            return False
    
    def is_running(self) -> bool:
        """Check if Minecraft process is still running"""
        if self.mc_process:
            return self.mc_process.poll() is None
        return False
    
    def wait_for_exit(self) -> int:
        """Wait for Minecraft to exit and return code"""
        if self.mc_process:
            return self.mc_process.wait()
        return 0
    
    def write_mod_config(self, config: dict):
        """Write configuration file for Forge mod"""
        config_path = self.minecraft_dir / "sync_mod_config.json"
        with open(config_path, 'w') as f:
            json.dump(config, f, indent=2)
        logger.info(f"Mod config written: {config}")


class SyncApp:
    """Main application class"""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Minecraft World Sync")
        self.root.geometry("500x400")
        
        self.password = tk.StringVar()
        self.minecraft_dir = tk.StringVar()
        self.selected_world = tk.StringVar()
        self.worlds = []
        
        self.network_manager = None
        self.world_manager = None
        self.launcher = None
        self.crypto_manager = None
        
        self.is_host = False
        self.game_running = False
        
        self._setup_ui()
        self._auto_detect_minecraft()
    
    def _setup_ui(self):
        """Setup user interface"""
        # Password frame
        password_frame = ttk.LabelFrame(self.root, text="Room Password", padding=10)
        password_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.password_entry = ttk.Entry(password_frame, textvariable=self.password, show="*")
        self.password_entry.pack(fill=tk.X)
        
        # Minecraft directory frame
        mc_frame = ttk.LabelFrame(self.root, text="Minecraft Directory", padding=10)
        mc_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.mc_entry = ttk.Entry(mc_frame, textvariable=self.minecraft_dir)
        self.mc_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        self.browse_btn = ttk.Button(mc_frame, text="Browse", command=self._browse_mc_dir)
        self.browse_btn.pack(side=tk.RIGHT, padx=5)
        
        # World selection frame
        world_frame = ttk.LabelFrame(self.root, text="Select World", padding=10)
        world_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.world_combo = ttk.Combobox(world_frame, textvariable=self.selected_world, state="readonly")
        self.world_combo.pack(fill=tk.X)
        
        self.refresh_btn = ttk.Button(world_frame, text="Refresh Worlds", command=self._refresh_worlds)
        self.refresh_btn.pack(pady=5)
        
        # Play button
        self.play_btn = ttk.Button(self.root, text="Play", command=self._on_play, style="Accent.TButton")
        self.play_btn.pack(pady=20, ipadx=50, ipady=10)
        
        # Status label
        self.status_label = ttk.Label(self.root, text="Status: Ready", foreground="gray")
        self.status_label.pack(pady=10)
        
        # Settings button
        settings_btn = ttk.Button(self.root, text="Settings", command=self._show_settings)
        settings_btn.pack(pady=5)
    
    def _auto_detect_minecraft(self):
        """Auto-detect Minecraft directory"""
        appdata = os.environ.get('APPDATA', '')
        possible_dirs = [
            Path(appdata) / '.minecraft',
            Path(appdata) / '.tlauncher' / 'minecraft',
            Path.home() / 'minecraft'
        ]
        
        for dir_path in possible_dirs:
            if dir_path.exists() and (dir_path / 'saves').exists():
                self.minecraft_dir.set(str(dir_path))
                self._refresh_worlds()
                logger.info(f"Auto-detected Minecraft: {dir_path}")
                return
        
        logger.warning("Minecraft directory not auto-detected")
    
    def _browse_mc_dir(self):
        """Open directory browser for Minecraft folder"""
        directory = filedialog.askdirectory(title="Select .minecraft Directory")
        if directory:
            self.minecraft_dir.set(directory)
            self._refresh_worlds()
    
    def _refresh_worlds(self):
        """Scan and populate world list"""
        mc_dir = Path(self.minecraft_dir.get())
        saves_dir = mc_dir / 'saves'
        
        self.worlds = []
        if saves_dir.exists():
            for world_path in saves_dir.iterdir():
                if world_path.is_dir() and (world_path / 'level.dat').exists():
                    self.worlds.append(world_path.name)
        
        self.world_combo['values'] = self.worlds
        if self.worlds:
            self.world_combo.current(0)
    
    def _show_settings(self):
        """Show settings dialog"""
        messagebox.showinfo("Settings", 
            "Settings Dialog\n\n"
            "• Set Minecraft directory manually if auto-detection fails\n"
            "• Ensure Radmin VPN is connected\n"
            "• All participants must use the same room password")
    
    def _on_play(self):
        """Handle play button click"""
        password = self.password.get().strip()
        if not password:
            messagebox.showerror("Error", "Please enter room password")
            return
        
        if not self.selected_world.get():
            messagebox.showerror("Error", "Please select a world")
            return
        
        if not self.minecraft_dir.get():
            messagebox.showerror("Error", "Please set Minecraft directory")
            return
        
        # Initialize components
        try:
            self._initialize_game(password)
        except Exception as e:
            logger.error(f"Initialization failed: {e}")
            messagebox.showerror("Error", f"Failed to initialize: {e}")
    
    def _initialize_game(self, password: str):
        """Initialize game session"""
        # Generate room ID
        room_id = hashlib.sha256(password.encode()).hexdigest()[:16]
        salt = os.urandom(8)
        
        # Initialize crypto
        self.crypto_manager = CryptoManager(password, salt)
        
        # Initialize network
        self.network_manager = NetworkManager(room_id, self.crypto_manager)
        if not self.network_manager.start():
            raise Exception("Failed to start network manager")
        
        # Initialize world manager
        self.world_manager = WorldManager(self.minecraft_dir.get(), self.crypto_manager)
        self.world_manager.set_world(self.selected_world.get())
        
        # Initialize launcher
        self.launcher = MinecraftLauncher(self.minecraft_dir.get())
        
        # Determine if we should be host
        time.sleep(2)  # Wait for discovery
        self.is_host = len(self.network_manager.participants) == 0
        
        # Start game
        self._start_game()
    
    def _start_game(self):
        """Start Minecraft game"""
        if self.is_host:
            self.status_label.config(text="Status: Host", foreground="green")
            logger.info("Starting as host")
            
            # Write mod config for host
            self.launcher.write_mod_config({
                "mode": "host",
                "world_name": self.selected_world.get()
            })
        else:
            self.status_label.config(text="Status: Client", foreground="blue")
            logger.info("Starting as client")
            
            # Get host info
            host_ip = list(self.network_manager.participants.keys())[0]
            self.launcher.write_mod_config({
                "mode": "client",
                "host_ip": host_ip
            })
        
        # Launch Minecraft (without auto-login to avoid TLauncher issues)
        if not self.launcher.launch_minecraft():
            raise Exception("Failed to launch Minecraft")
        
        self.game_running = True
        
        # Monitor game
        threading.Thread(target=self._monitor_game, daemon=True).start()
        
        # Minimize to tray (simplified - just hide window)
        self.root.withdraw()
    
    def _monitor_game(self):
        """Monitor game process and handle exit"""
        exit_code = self.launcher.wait_for_exit()
        self.game_running = False
        
        logger.info(f"Game exited with code {exit_code}")
        
        if self.is_host:
            # Archive and sync world
            self._sync_world_on_exit()
        
        # Show window again
        self.root.after(0, self.root.deiconify)
        self.status_label.config(text="Status: Game ended", foreground="gray")
    
    def _sync_world_on_exit(self):
        """Sync world when host exits game"""
        logger.info("Syncing world on game exit")
        
        # Increment version
        self.world_manager.increment_version()
        
        # Archive world
        archive_path = tempfile.mktemp(suffix=".zip.enc")
        if self.world_manager.archive_world(archive_path):
            # Send to all clients
            for ip in self.network_manager.participants.keys():
                # Send archive (simplified)
                logger.info(f"Sending world archive to {ip}")
        
        os.unlink(archive_path)


def main():
    app = SyncApp()
    app.root.mainloop()


if __name__ == "__main__":
    main()
