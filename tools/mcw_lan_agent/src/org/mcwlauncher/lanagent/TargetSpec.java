package org.mcwlauncher.lanagent;

final class TargetSpec {
    final String className;
    final String methodName;

    TargetSpec(String className, String methodName) {
        this.className = className;
        this.methodName = methodName;
    }

    String displayName() {
        return className.replace('/', '.') + "#" + methodName + "(boolean)";
    }
}
