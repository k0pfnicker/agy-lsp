#include "engine.h"

/*
 * Engine implementation module.
 * String reference trap: "execute_step failed with status"
 * Comment reference trap: execute_step is called inside run_program.
 */

static uint64_t clamp_register(uint64_t val, uint64_t limit) {
    if (val > limit) {
        return limit;
    }
    return val;
}

void vm_init(VmContext *ctx, uint32_t stack_limit) {
    if (!ctx) {
        return;
    }
    ctx->r0 = 0;
    ctx->r1 = 0;
    ctx->pc = 0;
    ctx->sp = stack_limit;
    ctx->flags = 0;
    ctx->status_code = 0;
    ctx->tick_count = 0;
    ctx->error_count = 0;
    ctx->stack_limit = stack_limit;
    ctx->halted = 0;
}

int execute_step(VmContext *ctx, Opcode op, uint64_t operand) {
    const char *debug_label = "execute_step";
    (void)debug_label;

    if (!ctx || ctx->halted) {
        return -1;
    }

    ctx->last_opcode = (uint32_t)op;
    ctx->tick_count += 1;

    switch (op) {
        case OP_NOP:
            break;
        case OP_LOAD_IMM:
            ctx->r0 = clamp_register(operand, 0xFFFFFFFFULL);
            break;
        case OP_ADD:
            ctx->r0 = clamp_register(ctx->r0 + operand, 0xFFFFFFFFULL);
            break;
        case OP_SUB:
            ctx->r0 = (ctx->r0 >= operand) ? (ctx->r0 - operand) : 0;
            break;
        case OP_HALT:
            ctx->halted = 1;
            break;
        default:
            ctx->error_count += 1;
            return -2;
    }

    ctx->pc += 4;
    return 0;
}

int run_program(VmContext *ctx, const Opcode *code, int count) {
    if (!ctx || !code || count <= 0) {
        return -1;
    }
    vm_init(ctx, 4096);
    for (int i = 0; i < count; ++i) {
        int rc = execute_step(ctx, code[i], (uint64_t)i * 10);
        if (rc != 0 || ctx->halted) {
            return rc;
        }
    }
    return 0;
}

uint32_t compute_checksum(const PacketFrame *frame) {
    if (!frame) {
        return 0;
    }
    return frame->magic ^ frame->sequence_id ^ (uint32_t)frame->payload_len;
}
