/* Complete frozen EfficientAD: all CNN ops in PL, scoring/control on ARM.
 * Use ONLY the new efficientad_engine bitstream and matching PS initialization.
 */
#include <stdint.h>
#include <string.h>
#include "xil_types.h"
#include "xil_io.h"
#include "xil_cache.h"
#include "xil_printf.h"
#include "xiltimer.h"
#include "xstatus.h"
#include "ea_model_data.h"
#include "ea_score.h"
#include "ea_expected.h"

#define ENGINE_BASE ((UINTPTR)0x43C00000U)
#define ENGINE_TIMEOUT_SECONDS 300U
static uint64_t buffers[2][EA_BUFFER_WORDS] __attribute__((aligned(64)));
static uint64_t teacher_features[150528] __attribute__((aligned(64)));
static uint64_t student_features[301056] __attribute__((aligned(64)));
static uint64_t ae_features[150528] __attribute__((aligned(64)));
static float fused[56U*56U];
/* JTAG-readable mailbox: flushed to DDR, separate from serial-port ownership. */
volatile uint32_t EaStatus[64] __attribute__((aligned(64)));
static void status_flush(void) {Xil_DCacheFlushRange((INTPTR)EaStatus,sizeof(EaStatus));}
static int fail_return(unsigned code) {
    EaStatus[1]=0xffffffffU;EaStatus[5]=code;status_flush();return XST_FAILURE;
}

static uint32_t crc_bytes(const void *data,unsigned bytes) {
    const uint8_t *p=(const uint8_t*)data;
    uint32_t crc=0xffffffffU;unsigned i,bit;
    for(i=0;i<bytes;++i) {
        crc^=p[i];
        for(bit=0;bit<8U;++bit)crc=(crc>>1)^((crc&1U)?0xedb88320U:0U);
    }
    return crc^0xffffffffU;
}
static void reg_write(unsigned off,unsigned value) {Xil_Out32(ENGINE_BASE+off,value);}
static unsigned reg_read(unsigned off) {return Xil_In32(ENGINE_BASE+off);}
static int in_ddr(const void *p,unsigned bytes) {
    UINTPTR a=(UINTPTR)p;
    return !(a&63U) && a>=0x00100000U && a+bytes-1U<=0x3fffffffU;
}
static int run_op(const EaOp *o,const uint64_t *src,uint64_t *dst) {
    XTime begin,now;
    unsigned src_bytes=o->ih*o->iw*((o->cin+7U)/8U)*8U;
    unsigned dst_bytes=o->oh*o->ow*(o->cout/8U)*8U;
    if(dst_bytes>sizeof(buffers[0]) || !in_ddr(src,src_bytes) || !in_ddr(dst,dst_bytes))return 1;
    Xil_DCacheFlushRange((INTPTR)src,src_bytes);
    Xil_DCacheFlushRange((INTPTR)dst,dst_bytes);
    // m_axi base zero; scalar addresses are 64-bit-word offsets into PS DDR.
    reg_write(0x18,0);reg_write(0x1c,0);
    unsigned base=(unsigned)((UINTPTR)ea_blob>>3);
    unsigned args[18]={o->opcode,(unsigned)((UINTPTR)src>>3),(unsigned)((UINTPTR)dst>>3),
        base+o->wo,base+o->bo,base+o->mo,o->ih,o->iw,o->cin,o->cout,o->kernel,
        o->stride,o->pad,o->relu,o->pool,o->oh,o->ow,base+o->co};
    unsigned i;
    for(i=0;i<18U;++i)reg_write(0x28U+i*8U,args[i]);
    XTime_GetTime(&begin);reg_write(0x00,1U);
    while(!(reg_read(0x00)&2U)) {
        XTime_GetTime(&now);
        if(now-begin>(XTime)(COUNTS_PER_SECOND)*ENGINE_TIMEOUT_SECONDS) {
            xil_printf("FAIL: engine timeout, reset the system before retry\r\n");return 2;
        }
    }
    if(reg_read(0x10)!=0U) {
        xil_printf("FAIL: engine returned status=%u\r\n",reg_read(0x10));return 3;
    }
    Xil_DCacheInvalidateRange((INTPTR)dst,dst_bytes);
    return 0;
}
static void print_float6(float value) {
    double a=(double)value;
    if(a<0.0){xil_printf("-");a=-a;}
    unsigned integer=(unsigned)a;
    unsigned fraction=(unsigned)((a-(double)integer)*1000000.0+0.5);
    if(fraction>=1000000U){++integer;fraction=0;}
    xil_printf("%u.%06u",integer,fraction);
}
int main(void) {
    static const char *const net_names[3]={"teacher","student","autoencoder"};
    static const char *const image_names[2]={"D19_01","N17_03"};
    unsigned image,net,step;
    Xil_ICacheEnable();Xil_DCacheEnable();
    EaStatus[0]=0x45414631U;EaStatus[1]=1U;status_flush();
    xil_printf("\r\n-- COMPLETE EFFICIENTAD PL test --\r\n");
    xil_printf("Bundle: tie_mount_20261026_3000step_dedupval\r\n");
    xil_printf("PL: 22 Conv + ReLU/AvgPool + 7 Resize; PS: dispatch, scoring\r\n");
    xil_printf("Engine=0x%08x, embedded weights=%u bytes\r\n",(unsigned)ENGINE_BASE,(unsigned)sizeof(ea_blob));
    xil_printf("Quantization is bring-up INT8; checks use its own golden, not FP32 accuracy.\r\n");
    if(!in_ddr(ea_blob,sizeof(ea_blob)))return fail_return(1U);
    Xil_DCacheFlushRange((INTPTR)ea_blob,sizeof(ea_blob));
    for(image=0;image<2U;++image) {
        XTime start,end;XTime_GetTime(&start);
        xil_printf("Image %u/2: %s\r\n",image+1U,image_names[image]);
        for(net=0;net<3U;++net) {
            const uint64_t *src=ea_inputs[image];
            for(step=0;step<ea_net_count[net];++step) {
                unsigned oi=ea_net_begin[net]+step;
                const EaOp *o=ea_ops+oi;
                uint64_t *dst=buffers[step&1U];
                EaStatus[1]=2U;EaStatus[2]=image;EaStatus[3]=oi;status_flush();
                xil_printf("  %u/29 %s...\r\n",oi+1U,o->name);
                if(run_op(o,src,dst)!=0)return fail_return(0x100U+oi);
                unsigned bytes=o->oh*o->ow*o->cout;
                uint32_t crc=crc_bytes(dst,bytes);
                if(crc!=o->crc[image]) {
                    EaStatus[14]=crc;EaStatus[15]=o->crc[image];
                    xil_printf("FAIL: stage CRC=%08x expected=%08x\r\n",crc,o->crc[image]);return fail_return(0x200U+oi);
                }
                EaStatus[4]=crc;EaStatus[12U+image]=oi+1U;status_flush();
                xil_printf("  PASS CRC=%08x shape=%ux%ux%u\r\n",crc,o->oh,o->ow,o->cout);
                src=dst;
            }
            uint64_t *saved=net==0?teacher_features:net==1?student_features:ae_features;
            unsigned bytes=56U*56U*(net==1?768U:384U);
            memcpy(saved,src,bytes);
            xil_printf("%s NETWORK PASSED\r\n",net_names[net]);
        }
        float scales[3];
        for(net=0;net<3U;++net)scales[net]=ea_ops[ea_net_begin[net]+ea_net_count[net]-1U].scale;
        float quantiles[4]={ea_q_st_start,ea_q_st_end,ea_q_ae_start,ea_q_ae_end};
        float score=ea_compute_score((const int8_t*)teacher_features,(const int8_t*)student_features,
            (const int8_t*)ae_features,scales[0],scales[1],scales[2],ea_teacher_mean,ea_teacher_std,quantiles,fused);
        float difference=score-ea_expected_scores[image];if(difference<0)difference=-difference;
        if(!(difference<=0.00002f)) {
            xil_printf("FAIL: score differs from INT8 reference\r\n");return fail_return(0x300U+image);
        }
        xil_printf("SCORE=");print_float6(score);xil_printf(" threshold=");print_float6(ea_threshold);
        xil_printf(" predicted=%s\r\n",score>ea_threshold?"DEFECT":"NORMAL");
        XTime_GetTime(&end);
        uint32_t score_bits;memcpy(&score_bits,&score,4);
        EaStatus[6U+image]=score_bits;EaStatus[8U+image]=(score>ea_threshold);
        EaStatus[10U+image]=(unsigned)((end-start)*1000U/(XTime)(COUNTS_PER_SECOND));
        EaStatus[1]=3U;status_flush();
        xil_printf("Image %s FULL MODEL COMPUTE PASS, total=%u ms (checks included)\r\n",
            image_names[image],(unsigned)((end-start)*1000U/(XTime)(COUNTS_PER_SECOND)));
    }
    xil_printf("COMPLETE EFFICIENTAD PL TEST PASSED: 2 images, all 3 networks.\r\n");
    EaStatus[1]=4U;status_flush();
    return XST_SUCCESS;
}
