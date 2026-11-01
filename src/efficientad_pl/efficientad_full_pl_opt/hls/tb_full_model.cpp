// Execute the unmodified optimized HLS C++ source on both frozen real inputs.
#include "efficientad_engine.h"
#include "../generated/ea_model_data.h"
#include <vector>
#include <cstdio>
#include <chrono>
static uint32_t table[256];
static uint32_t crc(const std::vector<ap_uint<64> >&m,unsigned start,unsigned words) {
    uint32_t c=0xffffffffU;
    for(unsigned i=0;i<words;++i) {
        uint64_t v=m[start+i].to_uint64();
        for(unsigned b=0;b<8;++b){c=(c>>8)^table[(c^v)&255U];v>>=8;}
    }
    return c^0xffffffffU;
}
int main() {
    for(unsigned i=0;i<256;++i) {
        uint32_t c=i;for(unsigned b=0;b<8;++b)c=(c>>1)^((c&1)?0xedb88320U:0);table[i]=c;
    }
    unsigned blob_words=sizeof(ea_blob)/8, input=blob_words+8, buf=input+EA_INPUT_WORDS+8;
    std::vector<ap_uint<64> > mem(buf+2*EA_BUFFER_WORDS+8);
    for(unsigned i=0;i<blob_words;++i)mem[i]=ea_blob[i];
    auto begin=std::chrono::steady_clock::now();
    for(unsigned image=0;image<2;++image) {
        for(unsigned i=0;i<EA_INPUT_WORDS;++i)mem[input+i]=ea_inputs[image][i];
        for(unsigned net=0;net<3;++net) {
            unsigned src=input;
            for(unsigned step=0;step<ea_net_count[net];++step) {
                unsigned oi=ea_net_begin[net]+step,dst=buf+(step&1U)*EA_BUFFER_WORDS;
                const EaOp&o=ea_ops[oi];
                int status=efficientad_engine(mem.data(),o.opcode,src,dst,o.wo,o.bo,o.mo,
                    o.ih,o.iw,o.cin,o.cout,o.kernel,o.stride,o.pad,o.relu,o.pool,o.oh,o.ow,o.co);
                uint32_t c=crc(mem,dst,o.oh*o.ow*o.cout/8);
                if(status || c!=o.crc[image]) {
                    std::printf("FAIL image=%u stage=%u status=%d crc=%08x expected=%08x\n",image,oi,status,c,o.crc[image]);return 1;
                }
                double secs=std::chrono::duration<double>(std::chrono::steady_clock::now()-begin).count();
                std::printf("FULL CSIM image %u stage %u/29 %s PASS CRC=%08x host_elapsed=%.3fs\n",image+1,oi+1,o.name,c,secs);
                std::fflush(stdout);src=dst;
            }
        }
    }
    std::puts("OPTIMIZED FULL MODEL C SIMULATION PASSED: 58 stage CRC checks.");
    return 0;
}
