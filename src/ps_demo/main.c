/* Persistent image-in / anomaly-map-out service for the verified PL kernel.
 * JTAG transports bytes; it does not perform neural network computation.
 */
#include <stdint.h>
#include <string.h>
#include "xil_io.h"
#include "xil_cache.h"
#include "xiltimer.h"
#include "sleep.h"
#include "ea_model_data.h"
#include "ea_score.h"
#define ENGINE_BASE 0x43C00000U
volatile uint32_t DemoControl[64] __attribute__((aligned(64)));
uint64_t DemoInput[65536] __attribute__((aligned(64)));
float DemoFused[3136] __attribute__((aligned(64)));
uint32_t DemoTimes[29] __attribute__((aligned(64)));
static uint64_t buffers[2][EA_BUFFER_WORDS] __attribute__((aligned(64)));
static uint64_t tf[150528],sf[301056],af[150528];
static unsigned us(XTime a,XTime b){return (unsigned)((b-a)*1000000ULL/(XTime)(COUNTS_PER_SECOND));}
static void publish(void){Xil_DCacheFlushRange((INTPTR)DemoControl,sizeof(DemoControl));}
static unsigned run(const EaOp*o,const uint64_t*src,uint64_t*dst,unsigned oi){
    unsigned nb=o->ih*o->iw*((o->cin+7U)/8U)*8U;
    unsigned nd=o->oh*o->ow*o->cout;
    Xil_DCacheFlushRange((INTPTR)src,nb);
    Xil_DCacheFlushRange((INTPTR)dst,nd);
    Xil_Out32(ENGINE_BASE+0x18,0);Xil_Out32(ENGINE_BASE+0x1c,0);
    unsigned b=(unsigned)((UINTPTR)ea_blob>>3);
    unsigned args[18]={o->opcode,(unsigned)((UINTPTR)src>>3),(unsigned)((UINTPTR)dst>>3),
        b+o->wo,b+o->bo,b+o->mo,o->ih,o->iw,o->cin,o->cout,o->kernel,o->stride,o->pad,
        o->relu,o->pool,o->oh,o->ow,b+o->co};
    for(unsigned i=0;i<18;++i)Xil_Out32(ENGINE_BASE+0x28+i*8,args[i]);
    XTime a,z;XTime_GetTime(&a);Xil_Out32(ENGINE_BASE,1);
    while(!(Xil_In32(ENGINE_BASE)&2U)){
        XTime_GetTime(&z);if(z-a>(XTime)(COUNTS_PER_SECOND)*30U)return 1;
    }
    XTime_GetTime(&z);DemoTimes[oi]=us(a,z);
    if(Xil_In32(ENGINE_BASE+0x10))return 2;
    Xil_DCacheInvalidateRange((INTPTR)dst,nd);return 0;
}
int main(void){
    Xil_ICacheEnable();Xil_DCacheEnable();
    memset((void*)DemoControl,0,sizeof(DemoControl));
    DemoControl[0]=0x45414432U;DemoControl[13]=1;DemoControl[14]=0x4F563135U;
    memcpy((void*)(DemoControl+7),&ea_threshold,4);
    Xil_DCacheFlushRange((INTPTR)ea_blob,sizeof(ea_blob));publish();
    unsigned done=0;
    while(1){
        Xil_DCacheInvalidateRange((INTPTR)DemoControl,sizeof(DemoControl));
        unsigned seq=DemoControl[2];
        if(seq==done){usleep(1000);continue;}
        DemoControl[1]=1;DemoControl[5]=0;DemoControl[4]=0;publish();
        Xil_DCacheInvalidateRange((INTPTR)DemoInput,sizeof(DemoInput));
        XTime begin,end,sb,se;XTime_GetTime(&begin);
        unsigned err=0,kernel_us=0;
        for(unsigned net=0;net<3 && !err;++net){
            const uint64_t*src=DemoInput;
            for(unsigned step=0;step<ea_net_count[net];++step){
                unsigned oi=ea_net_begin[net]+step;
                uint64_t*dst=buffers[step&1];
                DemoControl[4]=oi;publish();
                unsigned status=run(ea_ops+oi,src,dst,oi);
                if(status){err=0x100U+oi*4+status;break;}
                kernel_us+=DemoTimes[oi];src=dst;
            }
            if(!err)memcpy(net==0?tf:net==1?sf:af,src,56U*56U*(net==1?768U:384U));
        }
        if(!err){
            float scales[3];for(unsigned n=0;n<3;++n)scales[n]=ea_ops[ea_net_begin[n]+ea_net_count[n]-1].scale;
            float q[4]={ea_q_st_start,ea_q_st_end,ea_q_ae_start,ea_q_ae_end};
            XTime_GetTime(&sb);
            float score=ea_compute_score((int8_t*)tf,(int8_t*)sf,(int8_t*)af,
                scales[0],scales[1],scales[2],ea_teacher_mean,ea_teacher_std,q,DemoFused);
            XTime_GetTime(&se);XTime_GetTime(&end);
            memcpy((void*)(DemoControl+6),&score,4);
            DemoControl[8]=kernel_us;DemoControl[9]=us(begin,end);DemoControl[10]=us(sb,se);
            DemoControl[4]=29;
            Xil_DCacheFlushRange((INTPTR)DemoFused,sizeof(DemoFused));
            Xil_DCacheFlushRange((INTPTR)DemoTimes,sizeof(DemoTimes));
        }
        done=seq;DemoControl[3]=seq;DemoControl[5]=err;DemoControl[1]=err?0xffffffffU:2U;publish();
    }
}
