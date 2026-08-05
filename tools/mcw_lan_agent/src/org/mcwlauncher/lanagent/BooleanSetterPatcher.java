package org.mcwlauncher.lanagent;

import java.nio.charset.StandardCharsets;
import java.util.Arrays;

/** A tiny class-file patcher specialized for one boolean setter. */
final class BooleanSetterPatcher {
    private static final int CLASS_MAGIC = 0xCAFEBABE;
    private static final String TARGET_DESCRIPTOR = "(Z)V";

    private BooleanSetterPatcher() {
    }

    static byte[] patch(byte[] original, String targetMethodName) {
        Cursor cursor = new Cursor(original);
        if (cursor.readU4() != CLASS_MAGIC) {
            throw new IllegalArgumentException("invalid class-file magic");
        }
        cursor.skip(4); // minor + major

        ConstantPool pool = ConstantPool.read(cursor);
        cursor.skip(6); // access_flags, this_class, super_class

        int interfaceCount = cursor.readU2();
        cursor.skip(interfaceCount * 2);
        skipMembers(cursor); // fields

        int methodCount = cursor.readU2();
        for (int index = 0; index < methodCount; index++) {
            cursor.skip(2); // access flags
            String methodName = pool.utf8(cursor.readU2());
            String descriptor = pool.utf8(cursor.readU2());
            int attributeCount = cursor.readU2();

            boolean target = targetMethodName.equals(methodName) && TARGET_DESCRIPTOR.equals(descriptor);
            for (int attributeIndex = 0; attributeIndex < attributeCount; attributeIndex++) {
                String attributeName = pool.utf8(cursor.readU2());
                int attributeLength = cursor.readU4();
                int attributeStart = cursor.position();

                if (target && "Code".equals(attributeName)) {
                    byte[] patched = patchCodeAttribute(original, attributeStart, attributeLength, pool);
                    if (patched != null) {
                        return patched;
                    }
                }
                cursor.moveTo(attributeStart + attributeLength);
            }
        }
        return null;
    }

    private static byte[] patchCodeAttribute(byte[] original, int attributeStart, int attributeLength, ConstantPool pool) {
        Cursor codeCursor = new Cursor(original, attributeStart, attributeStart + attributeLength);
        codeCursor.skip(4); // max_stack + max_locals
        int codeLength = codeCursor.readU4();
        int codeStart = codeCursor.position();
        int codeEnd = codeStart + codeLength;
        if (codeEnd > attributeStart + attributeLength) {
            throw new IllegalArgumentException("malformed Code attribute");
        }

        int patchOffset = -1;
        int patchLength = 0;
        for (int offset = codeStart; offset < codeEnd; offset++) {
            int opcode = original[offset] & 0xFF;
            int candidateLength = 0;
            int putFieldOffset = -1;

            if (opcode == 0x1B) { // iload_1
                candidateLength = 1;
                putFieldOffset = offset + 1;
            } else if (opcode == 0x15 && offset + 1 < codeEnd && (original[offset + 1] & 0xFF) == 1) { // iload 1
                candidateLength = 2;
                putFieldOffset = offset + 2;
            }

            if (candidateLength == 0 || putFieldOffset + 2 >= codeEnd || (original[putFieldOffset] & 0xFF) != 0xB5) {
                continue;
            }
            if (offset <= codeStart || (original[offset - 1] & 0xFF) != 0x2A) { // aload_0
                continue;
            }

            int fieldReference = readU2(original, putFieldOffset + 1);
            if (!"Z".equals(pool.fieldDescriptor(fieldReference))) {
                continue;
            }
            if (patchOffset != -1) {
                throw new IllegalArgumentException("setter contains multiple boolean field writes");
            }
            patchOffset = offset;
            patchLength = candidateLength;
        }

        if (patchOffset == -1) {
            return null;
        }

        byte[] patched = Arrays.copyOf(original, original.length);
        patched[patchOffset] = 0x03; // iconst_0
        if (patchLength == 2) {
            patched[patchOffset + 1] = 0x00; // nop; preserve bytecode offsets and stack-map frames
        }
        return patched;
    }

    private static void skipMembers(Cursor cursor) {
        int count = cursor.readU2();
        for (int index = 0; index < count; index++) {
            cursor.skip(6); // access, name, descriptor
            int attributes = cursor.readU2();
            for (int attribute = 0; attribute < attributes; attribute++) {
                cursor.skip(2);
                int length = cursor.readU4();
                cursor.skip(length);
            }
        }
    }

    private static int readU2(byte[] data, int offset) {
        if (offset < 0 || offset + 2 > data.length) {
            throw new IllegalArgumentException("class-file read outside bounds");
        }
        return ((data[offset] & 0xFF) << 8) | (data[offset + 1] & 0xFF);
    }

    private static final class ConstantPool {
        private final int[] tags;
        private final int[] first;
        private final int[] second;
        private final String[] utf8;

        private ConstantPool(int count) {
            this.tags = new int[count];
            this.first = new int[count];
            this.second = new int[count];
            this.utf8 = new String[count];
        }

        static ConstantPool read(Cursor cursor) {
            int count = cursor.readU2();
            ConstantPool pool = new ConstantPool(count);
            for (int index = 1; index < count; index++) {
                int tag = cursor.readU1();
                pool.tags[index] = tag;
                switch (tag) {
                    case 1: {
                        int length = cursor.readU2();
                        pool.utf8[index] = new String(cursor.readBytes(length), StandardCharsets.UTF_8);
                        break;
                    }
                    case 3:
                    case 4:
                        cursor.skip(4);
                        break;
                    case 5:
                    case 6:
                        cursor.skip(8);
                        index++;
                        break;
                    case 7:
                    case 8:
                    case 16:
                    case 19:
                    case 20:
                        pool.first[index] = cursor.readU2();
                        break;
                    case 9:
                    case 10:
                    case 11:
                    case 12:
                    case 17:
                    case 18:
                        pool.first[index] = cursor.readU2();
                        pool.second[index] = cursor.readU2();
                        break;
                    case 15:
                        pool.first[index] = cursor.readU1();
                        pool.second[index] = cursor.readU2();
                        break;
                    default:
                        throw new IllegalArgumentException("unsupported constant-pool tag " + tag);
                }
            }
            return pool;
        }

        String utf8(int index) {
            if (index <= 0 || index >= utf8.length || tags[index] != 1) {
                throw new IllegalArgumentException("invalid UTF-8 constant-pool reference");
            }
            return utf8[index];
        }

        String fieldDescriptor(int fieldReferenceIndex) {
            if (fieldReferenceIndex <= 0 || fieldReferenceIndex >= tags.length || tags[fieldReferenceIndex] != 9) {
                return "";
            }
            int nameAndTypeIndex = second[fieldReferenceIndex];
            if (nameAndTypeIndex <= 0 || nameAndTypeIndex >= tags.length || tags[nameAndTypeIndex] != 12) {
                return "";
            }
            return utf8(second[nameAndTypeIndex]);
        }
    }

    private static final class Cursor {
        private final byte[] data;
        private final int limit;
        private int offset;

        Cursor(byte[] data) {
            this(data, 0, data.length);
        }

        Cursor(byte[] data, int offset, int limit) {
            this.data = data;
            this.offset = offset;
            this.limit = Math.min(limit, data.length);
        }

        int position() {
            return offset;
        }

        void moveTo(int newOffset) {
            if (newOffset < 0 || newOffset > limit) {
                throw new IllegalArgumentException("class-file seek outside bounds");
            }
            offset = newOffset;
        }

        int readU1() {
            require(1);
            return data[offset++] & 0xFF;
        }

        int readU2() {
            require(2);
            int value = ((data[offset] & 0xFF) << 8) | (data[offset + 1] & 0xFF);
            offset += 2;
            return value;
        }

        int readU4() {
            require(4);
            long value = ((long) (data[offset] & 0xFF) << 24)
                | ((long) (data[offset + 1] & 0xFF) << 16)
                | ((long) (data[offset + 2] & 0xFF) << 8)
                | (long) (data[offset + 3] & 0xFF);
            offset += 4;
            return (int) value;
        }

        byte[] readBytes(int length) {
            require(length);
            byte[] value = Arrays.copyOfRange(data, offset, offset + length);
            offset += length;
            return value;
        }

        void skip(int length) {
            require(length);
            offset += length;
        }

        private void require(int length) {
            if (length < 0 || offset + length > limit) {
                throw new IllegalArgumentException("truncated class file");
            }
        }
    }
}
