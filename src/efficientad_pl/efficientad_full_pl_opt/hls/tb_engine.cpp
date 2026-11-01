#include "efficientad_engine.h"
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <vector>
int main(int argc,char **argv) {
    const char *path=argc>1?argv[1]:"engine_tests.bin";
    unsigned limit=argc>2?unsigned(std::atoi(argv[2])):1000;
    unsigned first=argc>3?unsigned(std::atoi(argv[3])):0;
    std::ifstream f(path,std::ios::binary);
    char magic[4]; uint32_t count=0;
    f.read(magic,4); f.read(reinterpret_cast<char*>(&count),4);
    if(!f || magic[0]!='E' || magic[1]!='A' || magic[2]!='T' || magic[3]!='1') {
        std::printf("FAIL: cannot read test data %s\n",path); return 1;
    }
    unsigned passed=0;
    for(unsigned t=0;t<count && t<limit;++t) {
        uint32_t p[18],n;
        f.read(reinterpret_cast<char*>(p),sizeof(p));
        f.read(reinterpret_cast<char*>(&n),4);
        if(n>65536 || !f) return 2;
        std::vector<ap_uint<64> > mem(65536);
        std::vector<uint64_t> expected(n);
        for(unsigned i=0;i<n;++i) {
            uint64_t v; f.read(reinterpret_cast<char*>(&v),8); mem[i]=v;
        }
        f.read(reinterpret_cast<char*>(expected.data()),n*8);
        if(!f) return 3;
        if(t<first) continue;
        int status=efficientad_engine(mem.data(),p[0],p[1],p[2],p[3],p[4],p[5],p[6],p[7],p[8],
            p[9],p[10],p[11],p[12],p[13],p[14],p[15],p[16],p[17]);
        if(status) {std::printf("FAIL case %u status=%d\n",t,status); return 4;}
        for(unsigned i=0;i<n;++i) {
            if(mem[i].to_uint64()!=expected[i]) {
                std::printf("FAIL case %u op=%u K=%u Cin=%u word=%u actual=%016llx expected=%016llx\n",
                    t,p[0],p[10],p[8],i,(unsigned long long)mem[i].to_uint64(),(unsigned long long)expected[i]);
                return 5;
            }
        }
        ++passed;
        std::printf("Case %u/%u PASS: op=%u K=%u Cin=%u pool=%u shape=%ux%u -> %ux%u\n",
            t+1,count,p[0],p[10],p[8],p[14],p[6],p[7],p[15],p[16]);
    }
    std::printf("EFFICIENTAD ENGINE TEST PASSED: %u cases.\n",passed);
    return 0;
}
