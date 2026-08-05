package org.mcwlauncher.lanagent;

import java.io.IOException;
import java.lang.instrument.Instrumentation;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardOpenOption;
import java.time.OffsetDateTime;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

/**
 * Minimal host-side LAN agent used by MCW Launcher.
 *
 * <p>The agent is intentionally dormant unless {@code -Dmcw.lan.offline=true}
 * is present. It does not touch Authlib, tokens, networking, or Minecraft
 * files. Its only transformer targets the resolved runtime equivalents of
 * MinecraftServer#setUsesAuthentication(boolean) and forces the value written
 * by that setter to {@code false}.</p>
 */
public final class McwLanAgent {
    static final String ENABLE_PROPERTY = "mcw.lan.offline";
    static final String TARGETS_PROPERTY = "mcw.lan.targets";
    static final String TARGET_CLASS_PROPERTY = "mcw.lan.target.class";
    static final String TARGET_METHOD_PROPERTY = "mcw.lan.target.method";
    static final String LOG_PATH_PROPERTY = "mcw.lan.log";
    static final String LOADER_PROPERTY = "mcw.lan.loader";
    static final String DEFAULT_TARGET_CLASS = "net/minecraft/server/MinecraftServer";
    static final String DEFAULT_TARGET_METHOD = "setUsesAuthentication";
    private static final int MAX_TARGETS = 12;
    private static final Object LOG_LOCK = new Object();
    private static boolean fileLogFailureReported;

    private McwLanAgent() {
    }

    public static void premain(String agentArguments, Instrumentation instrumentation) {
        log("premain entered; Java " + System.getProperty("java.version", "unknown")
            + "; loader=" + System.getProperty(LOADER_PROPERTY, "unknown"));
        if (!Boolean.getBoolean(ENABLE_PROPERTY)) {
            log("disabled; the enable property is not true");
            return;
        }

        List<TargetSpec> targets = parseTargets();
        if (targets.isEmpty()) {
            log("refused empty or unsafe target configuration");
            return;
        }

        final LanOfflineTransformer transformer = new LanOfflineTransformer(targets);
        instrumentation.addTransformer(transformer, false);
        Runtime.getRuntime().addShutdownHook(new Thread(new Runnable() {
            @Override
            public void run() {
                log(transformer.shutdownSummary());
            }
        }, "mcw-lan-agent-summary"));

        log("enabled with " + targets.size() + " resolved target candidate(s)");
        for (TargetSpec target : targets) {
            log("candidate: " + target.displayName());
        }
    }

    static List<TargetSpec> parseTargets() {
        String configured = System.getProperty(TARGETS_PROPERTY, "").trim();
        List<TargetSpec> result = new ArrayList<TargetSpec>();
        Set<String> seen = new LinkedHashSet<String>();

        if (!configured.isEmpty()) {
            String[] entries = configured.split(";");
            for (String entry : entries) {
                if (result.size() >= MAX_TARGETS) {
                    break;
                }
                int separator = entry.lastIndexOf('#');
                if (separator <= 0 || separator >= entry.length() - 1) {
                    continue;
                }
                addTarget(result, seen, entry.substring(0, separator), entry.substring(separator + 1));
            }
        }

        if (result.isEmpty()) {
            addTarget(
                result,
                seen,
                System.getProperty(TARGET_CLASS_PROPERTY, DEFAULT_TARGET_CLASS),
                System.getProperty(TARGET_METHOD_PROPERTY, DEFAULT_TARGET_METHOD)
            );
        }
        return result;
    }

    private static void addTarget(List<TargetSpec> targets, Set<String> seen, String rawClassName, String rawMethodName) {
        String className = normalizeClassName(rawClassName);
        String methodName = rawMethodName == null ? "" : rawMethodName.trim();
        if (!isSafeMinecraftTarget(className, methodName)) {
            log("ignored unsafe target candidate");
            return;
        }
        String key = className + "#" + methodName;
        if (seen.add(key)) {
            targets.add(new TargetSpec(className, methodName));
        }
    }

    static String normalizeClassName(String value) {
        return value == null ? "" : value.trim().replace('.', '/');
    }

    static boolean isSafeMinecraftTarget(String className, String methodName) {
        boolean namedOrIntermediary = className.startsWith("net/minecraft/") && className.length() <= 240;
        boolean officialObfuscated = className.matches("[A-Za-z_$][A-Za-z0-9_$]{0,31}");
        return (namedOrIntermediary || officialObfuscated)
            && methodName.matches("[A-Za-z_$][A-Za-z0-9_$]{0,127}");
    }

    static void log(String message) {
        String line = OffsetDateTime.now() + " [MCW LAN Agent] " + message;
        System.err.println(line);

        String configuredPath = System.getProperty(LOG_PATH_PROPERTY, "").trim();
        if (configuredPath.isEmpty()) {
            return;
        }

        synchronized (LOG_LOCK) {
            try {
                Path path = Paths.get(configuredPath).toAbsolutePath().normalize();
                Path parent = path.getParent();
                if (parent != null) {
                    Files.createDirectories(parent);
                }
                Files.write(
                    path,
                    (line + System.lineSeparator()).getBytes(StandardCharsets.UTF_8),
                    StandardOpenOption.CREATE,
                    StandardOpenOption.APPEND
                );
            } catch (IOException | RuntimeException exception) {
                if (!fileLogFailureReported) {
                    fileLogFailureReported = true;
                    System.err.println("[MCW LAN Agent] could not write the dedicated log: " + exception.getMessage());
                }
            }
        }
    }
}
