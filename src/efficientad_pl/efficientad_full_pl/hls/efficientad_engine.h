#ifndef EFFICIENTAD_ENGINE_H
#define EFFICIENTAD_ENGINE_H
#include <ap_int.h>
int efficientad_engine(ap_uint<64> *mem, unsigned opcode,
    unsigned src, unsigned dst, unsigned weights, unsigned biases, unsigned multipliers,
    unsigned ih, unsigned iw, unsigned cin, unsigned cout, unsigned kernel,
    unsigned stride, unsigned pad, unsigned relu, unsigned pool,
    unsigned oh, unsigned ow, unsigned coordinates);
#endif
