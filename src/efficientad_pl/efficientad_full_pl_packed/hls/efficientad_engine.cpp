// Dynamic DDR-backed INT8 convolution / bilinear resize for frozen EfficientAD.
// Dot products reuse unmodified Xilinx FINN mac.hpp (BSD-3-Clause).
#include "efficientad_engine.h"
#include <hls_stream.h>
#include "vendor/finn-hlslib/mac.hpp"

static const unsigned PE=32, SIMD=8, MAX_KWORDS=512;

// DSP48E1 signed 25x18 multiplication. Pack two signed INT8 weights
// at spacing 16 and share one signed input. Negative low product borrows
// from the high half; add it back before returning the second product.
static void paired_mul(ap_int<8> x,ap_int<8> w0,ap_int<8> w1,
                       ap_int<16>&p0,ap_int<16>&p1) {
#pragma HLS INLINE
    ap_int<25> packed=(ap_int<25>(w1)<<16)+ap_int<25>(w0);
    ap_int<33> product=mul(packed,x,ap_resource_dsp());
    p0=product.range(15,0);
    ap_int<17> high=product.range(32,16);
    p1=high+(p0<0 ? 1 : 0);
}

static ap_int<8> requant(ap_int<32> a, ap_int<32> m, bool relu) {
#pragma HLS INLINE off
    ap_int<64> product=ap_int<64>(a)*m;
    ap_int<64> magnitude=product;
    if(product<0) magnitude=-product;
    ap_int<64> q=(magnitude+(ap_int<64>(1)<<29))>>30;
    if(product<0) q=-q;
    if(relu && q<0) q=0;
    if(q>127) q=127;
    if(q< -127) q=-127;
    return ap_int<8>(q);
}

static ap_int<8> average4(ap_int<8> a, ap_int<8> b, ap_int<8> c, ap_int<8> d) {
#pragma HLS INLINE
    ap_int<12> s=ap_int<12>(a)+b+c+d;
    ap_int<12> q=s;
    if(s<0) q=-s;
    q=(q+2)>>2;
    if(s<0) q=-q;
    return ap_int<8>(q);
}

static void conv_layer(ap_uint<64>*mem,unsigned src,unsigned dst,unsigned wo,
    unsigned bo,unsigned mo,unsigned ih,unsigned iw,unsigned cin,unsigned cout,
    unsigned k,unsigned stride,unsigned pad,bool relu,bool pool,unsigned oh,unsigned ow) {
#pragma HLS INLINE off
    ap_uint<64> wc[PE][MAX_KWORDS];
    // Circular k-row cache: <=8192 words for every frozen model layer.
    ap_uint<64> rows[8192];
    int tags[8];
    ap_uint<14> row_base[8];
    bool row_valid[8];
#pragma HLS ARRAY_PARTITION variable=tags complete
#pragma HLS ARRAY_PARTITION variable=row_base complete
#pragma HLS ARRAY_PARTITION variable=row_valid complete
    ap_int<8> top[256][PE], left[PE], q[PE];
    ap_int<32> bias[PE], mult[PE], accum[PE];
#pragma HLS ARRAY_PARTITION variable=wc complete dim=1
#pragma HLS BIND_STORAGE variable=wc type=ram_1p impl=bram
#pragma HLS BIND_STORAGE variable=rows type=ram_1p impl=bram
#pragma HLS ARRAY_PARTITION variable=top complete dim=2
#pragma HLS BIND_STORAGE variable=top type=ram_2p impl=lutram
#pragma HLS ARRAY_PARTITION variable=left complete
#pragma HLS ARRAY_PARTITION variable=q complete
#pragma HLS ARRAY_PARTITION variable=bias complete
#pragma HLS ARRAY_PARTITION variable=mult complete
#pragma HLS ARRAY_PARTITION variable=accum complete
    unsigned cg=(cin+7)/8, og=cout/8, kw=k*k*cg;
    unsigned ch=(ih+2*pad-k)/stride+1, cw=(iw+2*pad-k)/stride+1;
    for(unsigned oc=0;oc<cout;oc+=PE) {
        for(unsigned p=0;p<PE;++p) {
            bias[p]=oc+p<cout ? ap_int<32>(mem[bo+oc+p]) : ap_int<32>(0);
            mult[p]=oc+p<cout ? ap_int<32>(mem[mo+oc+p]) : ap_int<32>(0);
            for(unsigned z=0;z<kw;++z) {
#pragma HLS PIPELINE II=1
#pragma HLS LOOP_TRIPCOUNT min=16 max=512
                wc[p][z]=oc+p<cout ? mem[wo+(oc+p)*kw+z] : ap_uint<64>(0);
            }
        }
        for(unsigned ky=0;ky<8;++ky) tags[ky]=-1000;
        for(unsigned y=0;y<ch;++y) {
          // DDR reads are contiguous full rows and reused across all x windows.
          for(unsigned ky=0;ky<k;++ky) {
            int sy=int(y*stride+ky)-int(pad);
            bool valid=sy>=0 && sy<int(ih);
            row_valid[ky]=valid;
            if(valid) {
                unsigned slot=unsigned(sy)%k;
                unsigned base=slot*iw*cg;
                row_base[ky]=base;
                if(tags[slot]!=sy) {
                    for(unsigned r=0;r<iw*cg;++r) {
#pragma HLS PIPELINE II=1
                        rows[base+r]=mem[src+unsigned(sy)*iw*cg+r];
                    }
                    tags[slot]=sy;
                }
            } else row_base[ky]=0;
          }
          for(unsigned x=0;x<cw;++x) {
            for(unsigned p=0;p<PE;++p) {
#pragma HLS UNROLL
                accum[p]=bias[p];
            }
            unsigned z=0;
            // Read cached windows directly into MACs: no separate patch load.
            for(unsigned ky=0;ky<k;++ky) {
              for(unsigned kx=0;kx<k;++kx) {
                int sx=int(x*stride+kx)-int(pad);
                bool valid=row_valid[ky] && sx>=0 && sx<int(iw);
                unsigned base=row_base[ky]+unsigned(sx)*cg;
                for(unsigned g=0;g<cg;++g) {
#pragma HLS PIPELINE II=1
                    ap_uint<64> v=valid ? rows[base+g] : ap_uint<64>(0);
                    ap_int<8> iv[SIMD];
#pragma HLS ARRAY_PARTITION variable=iv complete
                    for(unsigned a=0;a<SIMD;++a) {
#pragma HLS UNROLL
                        iv[a]=v.range(8*a+7,8*a);
                    }
                    for(unsigned p=0;p<PE;p+=2) {
#pragma HLS UNROLL
                        ap_uint<64> w0=wc[p][z],w1=wc[p+1][z];
                        ap_int<32> sum0=0,sum1=0;
                        for(unsigned a=0;a<SIMD;++a) {
#pragma HLS UNROLL
                            ap_int<8> a0=w0.range(8*a+7,8*a),a1=w1.range(8*a+7,8*a);
                            ap_int<16> p0,p1;
                            paired_mul(iv[a],a0,a1,p0,p1);
                            sum0+=p0;sum1+=p1;
                        }
                        accum[p]+=sum0;accum[p+1]+=sum1;
                    }
                    ++z;
                }
              }
            }
            // Four shared requantizers; 32 results in eight issue cycles.
            for(unsigned p=0;p<PE;++p) {
#pragma HLS PIPELINE II=1
#pragma HLS UNROLL factor=4
                q[p]=requant(accum[p],mult[p],relu);
            }
            bool emit=!pool;
            unsigned oy=y, ox=x;
            if(pool) {
                emit=(y&1) && (x&1);
                oy=y/2; ox=x/2;
                for(unsigned p=0;p<PE;++p) {
#pragma HLS UNROLL
                    if(!(y&1)) top[x][p]=q[p];
                    else if(!(x&1)) left[p]=q[p];
                    else q[p]=average4(top[x-1][p],top[x][p],left[p],q[p]);
                }
            }
            if(emit) {
                for(unsigned group=0;group<PE/8;++group) {
#pragma HLS PIPELINE II=1
                    ap_uint<64> out=0;
                    for(unsigned s=0;s<SIMD;++s) {
#pragma HLS UNROLL
                        out.range(8*s+7,8*s)=ap_uint<8>(q[group*8+s]);
                    }
                    if(oc+group*8<cout) mem[dst+(oy*ow+ox)*og+oc/8+group]=out;
                }
            }
          }
        }
    }
    (void)oh;
}

static void resize_layer(ap_uint<64>*mem,unsigned src,unsigned dst,unsigned coords,
    unsigned ih,unsigned iw,unsigned channels,unsigned oh,unsigned ow) {
#pragma HLS INLINE off
    unsigned groups=channels/8;
    for(unsigned y=0;y<oh;++y) {
        ap_uint<64> cy=mem[coords+y];
        unsigned y0=cy.range(15,0), y1=cy.range(31,16);
        ap_uint<16> fy=cy.range(47,32);
        for(unsigned x=0;x<ow;++x) {
            ap_uint<64> cx=mem[coords+oh+x];
            unsigned x0=cx.range(15,0), x1=cx.range(31,16);
            ap_uint<16> fx=cx.range(47,32);
            for(unsigned g=0;g<groups;++g) {
                ap_uint<64> aa=mem[src+(y0*iw+x0)*groups+g];
                ap_uint<64> ab=mem[src+(y0*iw+x1)*groups+g];
                ap_uint<64> ba=mem[src+(y1*iw+x0)*groups+g];
                ap_uint<64> bb=mem[src+(y1*iw+x1)*groups+g];
                ap_uint<64> out=0;
                for(unsigned s=0;s<8;++s) {
#pragma HLS PIPELINE II=1
                    ap_int<8> a=aa.range(8*s+7,8*s), b=ab.range(8*s+7,8*s);
                    ap_int<8> c=ba.range(8*s+7,8*s), d=bb.range(8*s+7,8*s);
                    ap_uint<16> lx=32768-fx, ly=32768-fy;
                    ap_int<25> top=a*lx+b*fx;
                    ap_int<25> bot=c*lx+d*fx;
                    ap_int<44> sum=top*ly+bot*fy;
                    ap_int<44> mag=sum;
                    if(sum<0) mag=-sum;
                    ap_int<44> rounded=(mag+(ap_int<44>(1)<<29))>>30;
                    if(sum<0) rounded=-rounded;
                    if(rounded>127) rounded=127;
                    if(rounded< -127) rounded=-127;
                    out.range(8*s+7,8*s)=ap_uint<8>(ap_int<8>(rounded));
                }
                mem[dst+(y*ow+x)*groups+g]=out;
            }
        }
    }
    (void)ih;
}

int efficientad_engine(ap_uint<64> *mem,unsigned opcode,unsigned src,unsigned dst,
    unsigned weights,unsigned biases,unsigned multipliers,unsigned ih,unsigned iw,
    unsigned cin,unsigned cout,unsigned kernel,unsigned stride,unsigned pad,
    unsigned relu,unsigned pool,unsigned oh,unsigned ow,unsigned coordinates) {
#pragma HLS INTERFACE m_axi port=mem offset=slave bundle=ddr depth=65536 max_read_burst_length=16 max_write_burst_length=16 num_read_outstanding=4 num_write_outstanding=4
#pragma HLS INTERFACE s_axilite port=mem bundle=control offset=0x18
#pragma HLS INTERFACE s_axilite port=opcode bundle=control offset=0x28
#pragma HLS INTERFACE s_axilite port=src bundle=control offset=0x30
#pragma HLS INTERFACE s_axilite port=dst bundle=control offset=0x38
#pragma HLS INTERFACE s_axilite port=weights bundle=control offset=0x40
#pragma HLS INTERFACE s_axilite port=biases bundle=control offset=0x48
#pragma HLS INTERFACE s_axilite port=multipliers bundle=control offset=0x50
#pragma HLS INTERFACE s_axilite port=ih bundle=control offset=0x58
#pragma HLS INTERFACE s_axilite port=iw bundle=control offset=0x60
#pragma HLS INTERFACE s_axilite port=cin bundle=control offset=0x68
#pragma HLS INTERFACE s_axilite port=cout bundle=control offset=0x70
#pragma HLS INTERFACE s_axilite port=kernel bundle=control offset=0x78
#pragma HLS INTERFACE s_axilite port=stride bundle=control offset=0x80
#pragma HLS INTERFACE s_axilite port=pad bundle=control offset=0x88
#pragma HLS INTERFACE s_axilite port=relu bundle=control offset=0x90
#pragma HLS INTERFACE s_axilite port=pool bundle=control offset=0x98
#pragma HLS INTERFACE s_axilite port=oh bundle=control offset=0xa0
#pragma HLS INTERFACE s_axilite port=ow bundle=control offset=0xa8
#pragma HLS INTERFACE s_axilite port=coordinates bundle=control offset=0xb0
#pragma HLS INTERFACE s_axilite port=return bundle=control
    if(!ih || !iw || ih>256 || iw>256 || !oh || !ow || oh>256 || ow>256 ||
       !cin || cin>256 || (cin!=3 && cin%8) || src==dst) return 1;
    if(opcode==1) {
        if(cin==3 || cout!=cin) return 2;
        resize_layer(mem,src,dst,coordinates,ih,iw,cin,oh,ow);
        return 0;
    }
    if(opcode!=0 || !cout || cout>768 || cout%16 || !kernel || kernel>8 ||
       !stride || stride>2 || pad>2 || (cin+7)/8*kernel*kernel>MAX_KWORDS ||
       ih+2*pad<kernel || iw+2*pad<kernel || kernel*iw*((cin+7)/8)>8192) return 3;
    unsigned ch=(ih+2*pad-kernel)/stride+1, cw=(iw+2*pad-kernel)/stride+1;
    if(cw>256 || ch>256 || oh!=(pool ? ch/2 : ch) || ow!=(pool ? cw/2 : cw)) return 4;
    conv_layer(mem,src,dst,weights,biases,multipliers,ih,iw,cin,cout,kernel,stride,pad,relu!=0,pool!=0,oh,ow);
    return 0;
}
