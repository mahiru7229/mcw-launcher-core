package org.mcwlauncher.lanagent;

import java.lang.instrument.ClassFileTransformer;
import java.security.ProtectionDomain;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;

final class LanOfflineTransformer implements ClassFileTransformer {
    private final List<TargetSpec> targets;
    private final AtomicBoolean targetSeen = new AtomicBoolean(false);
    private final AtomicBoolean patched = new AtomicBoolean(false);
    private final AtomicBoolean patchFailed = new AtomicBoolean(false);

    LanOfflineTransformer(List<TargetSpec> targets) {
        this.targets = targets;
    }

    @Override
    public byte[] transform(
        ClassLoader loader,
        String className,
        Class<?> classBeingRedefined,
        ProtectionDomain protectionDomain,
        byte[] classfileBuffer
    ) {
        if (className == null || classfileBuffer == null) {
            return null;
        }

        boolean matchedClass = false;
        for (TargetSpec target : targets) {
            if (!target.className.equals(className)) {
                continue;
            }
            matchedClass = true;
            targetSeen.set(true);
            McwLanAgent.log("target class loaded by " + loaderName(loader) + ": " + className.replace('/', '.'));
            try {
                byte[] transformed = BooleanSetterPatcher.patch(classfileBuffer, target.methodName);
                if (transformed == null) {
                    McwLanAgent.log("candidate method was not found: " + target.displayName());
                    continue;
                }
                patched.set(true);
                McwLanAgent.log("patched " + target.displayName());
                return transformed;
            } catch (RuntimeException exception) {
                patchFailed.set(true);
                McwLanAgent.log("patch candidate failed safely for " + target.displayName() + ": " + exception.getMessage());
            }
        }

        if (matchedClass) {
            patchFailed.set(true);
            McwLanAgent.log("target class loaded, but none of its resolved setter candidates matched; leaving Minecraft unchanged");
        }
        return null;
    }

    String shutdownSummary() {
        if (patched.get()) {
            return "shutdown summary: LAN Offline Mode patch was applied successfully";
        }
        if (targetSeen.get() || patchFailed.get()) {
            return "shutdown summary: a resolved target class was found, but the patch was not applied; Minecraft stayed unchanged";
        }
        return "shutdown summary: none of the resolved target classes were loaded; runtime mappings may differ";
    }

    private static String loaderName(ClassLoader loader) {
        return loader == null ? "bootstrap loader" : loader.getClass().getName();
    }
}
