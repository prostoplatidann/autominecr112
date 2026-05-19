"""
Forge Mod for Minecraft 1.21.1
Automates LAN hosting and client connections for World Sync application.
"""

package com.worldsync.mod;

import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.ConnectScreen;
import net.minecraft.client.gui.screens.TitleScreen;
import net.minecraft.client.multiplayer.ServerAddress;
import net.minecraft.client.multiplayer.ServerData;
import net.minecraft.network.chat.Component;
import net.minecraft.server.integrated.IntegratedServer;
import net.minecraft.world.level.GameType;
import net.minecraftforge.api.distmarker.Dist;
import net.minecraftforge.api.distmarker.OnlyIn;
import net.minecraftforge.client.event.ClientPlayerNetworkEvent;
import net.minecraftforge.common.MinecraftForge;
import net.minecraftforge.event.TickEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.ModLoadingContext;
import net.minecraftforge.fml.common.Mod;
import net.minecraftforge.fml.event.lifecycle.FMLClientSetupEvent;
import net.minecraftforge.fml.javafmlmod.FMLJavaModLoadingContext;

import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;

import java.io.File;
import java.io.FileReader;
import java.io.FileWriter;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.Map;

@Mod("worldsync")
public class WorldSyncMod {
    private static final Logger LOGGER = LogManager.getLogger();
    private static final String MOD_CONFIG_FILE = "sync_mod_config.json";
    private static final String LAN_PORT_FILE = "sync_lan_port.txt";
    private static final String BACKUP_TRIGGER_FILE = "sync_backup_trigger.txt";
    
    private Map<String, Object> config;
    private boolean configLoaded = false;
    private boolean worldLoaded = false;
    private int ticksSinceBackup = 0;
    private static final int BACKUP_TICK_INTERVAL = 6000; // 5 minutes at 20 ticks/sec
    
    public WorldSyncMod() {
        FMLJavaModLoadingContext.get().getModEventBus().addListener(this::clientSetup);
        MinecraftForge.EVENT_BUS.register(this);
    }
    
    private void clientSetup(final FMLClientSetupEvent event) {
        LOGGER.info("WorldSync mod initialized");
        loadConfig();
    }
    
    @SubscribeEvent
    @OnlyIn(Dist.CLIENT)
    public void onClientTick(TickEvent.ClientTickEvent event) {
        if (event.phase != TickEvent.Phase.END) return;
        
        if (!configLoaded) {
            loadConfig();
            return;
        }
        
        if (config == null || config.isEmpty()) return;
        
        String mode = (String) config.get("mode");
        
        if ("host".equals(mode)) {
            handleHostMode();
        } else if ("client".equals(mode)) {
            handleClientMode();
        }
    }
    
    private void handleHostMode() {
        Minecraft mc = Minecraft.getInstance();
        
        // Auto-load world if not already loaded
        if (mc.level == null && !worldLoaded) {
            String worldName = (String) config.get("world_name");
            if (worldName != null && !worldName.isEmpty()) {
                LOGGER.info("Auto-loading world: {}", worldName);
                mc.execute(() -> {
                    try {
                        mc.loadLevel(worldName);
                        worldLoaded = true;
                    } catch (Exception e) {
                        LOGGER.error("Failed to load world", e);
                    }
                });
            }
            return;
        }
        
        // Open to LAN once world is loaded and server is running
        IntegratedServer server = mc.getSingleplayerServer();
        if (server != null && server.isPublished()) {
            // Already published to LAN
            return;
        }
        
        if (server != null && !server.isPublished()) {
            LOGGER.info("Opening world to LAN");
            mc.execute(() -> {
                try {
                    // Open to LAN with survival mode and cheats enabled
                    int port = server.shareToLan(GameType.SURVIVAL, true, 0);
                    LOGGER.info("LAN game started on port: {}", port);
                    
                    // Write port to file for Python app to read
                    writePortToFile(port);
                    
                    // Clear config after successful LAN setup
                    clearConfig();
                } catch (Exception e) {
                    LOGGER.error("Failed to open to LAN", e);
                }
            });
        }
        
        // Periodic backup trigger
        ticksSinceBackup++;
        if (ticksSinceBackup >= BACKUP_TICK_INTERVAL) {
            ticksSinceBackup = 0;
            triggerBackup();
        }
    }
    
    private void handleClientMode() {
        Minecraft mc = Minecraft.getInstance();
        
        // Auto-connect to host if in main menu
        if (mc.screen instanceof TitleScreen && !worldLoaded) {
            String hostIp = (String) config.get("host_ip");
            Integer port = (Integer) config.get("port");
            
            if (hostIp != null && !hostIp.isEmpty()) {
                LOGGER.info("Auto-connecting to {}:{}", hostIp, port != null ? port : 25565);
                
                mc.execute(() -> {
                    try {
                        int connectPort = port != null ? port : 25565;
                        ServerAddress address = new ServerAddress(hostIp, connectPort);
                        
                        ConnectScreen.startConnecting(
                            new TitleScreen(),
                            mc,
                            address,
                            new ServerData("WorldSync Server", hostIp + ":" + connectPort, ServerData.Type.OTHER),
                            true,
                            Component.literal("WorldSync")
                        );
                        
                        worldLoaded = true;
                        clearConfig();
                    } catch (Exception e) {
                        LOGGER.error("Failed to connect to server", e);
                    }
                });
            }
        }
    }
    
    private void loadConfig() {
        try {
            Path minecraftDir = Minecraft.getInstance().gameDirectory.toPath();
            File configFile = minecraftDir.resolve(MOD_CONFIG_FILE).toFile();
            
            if (configFile.exists()) {
                StringBuilder json = new StringBuilder();
                try (FileReader reader = new FileReader(configFile)) {
                    int c;
                    while ((c = reader.read()) != -1) {
                        json.append((char) c);
                    }
                }
                
                config = parseSimpleJson(json.toString());
                LOGGER.info("Config loaded: {}", config);
                configLoaded = true;
            }
        } catch (Exception e) {
            LOGGER.error("Failed to load config", e);
        }
    }
    
    @SuppressWarnings("unchecked")
    private Map<String, Object> parseSimpleJson(String json) {
        Map<String, Object> map = new HashMap<>();
        
        // Simple JSON parser for our specific format
        json = json.trim();
        if (json.startsWith("{") && json.endsWith("}")) {
            json = json.substring(1, json.length() - 1);
        }
        
        String[] pairs = json.split(",");
        for (String pair : pairs) {
            String[] kv = pair.split(":");
            if (kv.length == 2) {
                String key = kv[0].trim().replace("\"", "");
                String value = kv[1].trim().replace("\"", "");
                
                if (value.matches("\\d+")) {
                    map.put(key, Integer.parseInt(value));
                } else {
                    map.put(key, value);
                }
            }
        }
        
        return map;
    }
    
    private void writePortToFile(int port) {
        try {
            Path minecraftDir = Minecraft.getInstance().gameDirectory.toPath();
            File portFile = minecraftDir.resolve(LAN_PORT_FILE).toFile();
            
            try (FileWriter writer = new FileWriter(portFile)) {
                writer.write(String.valueOf(port));
            }
            
            LOGGER.info("Port written to file: {}", port);
        } catch (Exception e) {
            LOGGER.error("Failed to write port file", e);
        }
    }
    
    private void triggerBackup() {
        try {
            Path minecraftDir = Minecraft.getInstance().gameDirectory.toPath();
            File triggerFile = minecraftDir.resolve(BACKUP_TRIGGER_FILE).toFile();
            
            try (FileWriter writer = new FileWriter(triggerFile)) {
                writer.write(String.valueOf(System.currentTimeMillis()));
            }
            
            LOGGER.debug("Backup trigger created");
        } catch (Exception e) {
            LOGGER.error("Failed to create backup trigger", e);
        }
    }
    
    private void clearConfig() {
        try {
            Path minecraftDir = Minecraft.getInstance().gameDirectory.toPath();
            File configFile = minecraftDir.resolve(MOD_CONFIG_FILE).toFile();
            
            if (configFile.exists()) {
                configFile.delete();
                LOGGER.info("Config file cleared");
            }
            
            config = null;
            configLoaded = false;
        } catch (Exception e) {
            LOGGER.error("Failed to clear config", e);
        }
    }
}
