#ifndef ENGINE_H
#define ENGINE_H

/*
 * NOTE: Do not call execute_step directly from UI threads.
 * The legacy process_packet helper was replaced by execute_step.
 */

typedef unsigned char uint8_t;
typedef unsigned short uint16_t;
typedef unsigned int uint32_t;
typedef unsigned long long uint64_t;

typedef enum Opcode {
    OP_NOP = 0,
    OP_LOAD_IMM = 1,
    OP_LOAD_MEM = 2,
    OP_STORE_MEM = 3,
    OP_ADD = 4,
    OP_SUB = 5,
    OP_MUL = 6,
    OP_DIV = 7,
    OP_MOD = 8,
    OP_AND = 9,
    OP_OR = 10,
    OP_XOR = 11,
    OP_SHL = 12,
    OP_SHR = 13,
    OP_CMP = 14,
    OP_JMP = 15,
    OP_JZ = 16,
    OP_JNZ = 17,
    OP_CALL = 18,
    OP_RET = 19,
    OP_HALT = 20
} Opcode;

typedef struct VmContext {
    uint64_t r0;
    uint64_t r1;
    uint64_t r2;
    uint64_t r3;
    uint64_t r4;
    uint64_t r5;
    uint64_t r6;
    uint64_t r7;
    uint64_t r8;
    uint64_t r9;
    uint64_t r10;
    uint64_t r11;
    uint64_t r12;
    uint64_t r13;
    uint64_t r14;
    uint64_t r15;
    uint64_t pc;
    uint64_t sp;
    uint64_t bp;
    uint32_t flags;
    uint32_t status_code;
    uint32_t tick_count;
    uint32_t error_count;
    uint32_t last_opcode;
    uint32_t interrupt_mask;
    uint32_t pending_irq;
    uint32_t page_table_base;
    uint32_t stack_limit;
    uint32_t heap_base;
    uint32_t heap_limit;
    uint8_t privilege_level;
    uint8_t halted;
    uint8_t trace_enabled;
    uint8_t reserved;
} VmContext;

typedef struct PacketFrame {
    uint32_t magic;
    uint16_t version;
    uint16_t payload_len;
    uint32_t sequence_id;
    uint32_t checksum;
    uint64_t timestamp;
    uint8_t channel;
    uint8_t priority;
    uint8_t flags;
    uint8_t padding;
} PacketFrame;

void vm_init(VmContext *ctx, uint32_t stack_limit);
int execute_step(VmContext *ctx, Opcode op, uint64_t operand);
int run_program(VmContext *ctx, const Opcode *code, int count);
uint32_t compute_checksum(const PacketFrame *frame);

#endif /* ENGINE_H */
