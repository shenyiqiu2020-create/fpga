// Dynamic DDR-backed INT8 convolution / bilinear resize for frozen EfficientAD.
// Dot products reuse unmodified Xilinx FINN mac.hpp (BSD-3-Clause).
#include "efficientad_engine.h"
#include <hls_stream.h>
#include "vendor/finn-hlslib/mac.hpp"

static const unsigned PE=40, SIMD=8, MAX_KWORDS=512;

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

// Each FIFO packet carries one pixel's 40 exact INT32 accumulators.
// MAC and post-processing have independent state and overlap across x positions.
typedef ap_uint<PE*32> PixelSums;
static void mac_row(const ap_uint<64> rows[8192],
    const ap_uint<64> wc[PE][MAX_KWORDS], const ap_int<32> bias[PE],
    const ap_uint<14> row_base[8], const bool row_valid[8],
    ap_uint<6> cg, ap_uint<10> kw, ap_uint<4> k, ap_uint<2> stride,
    ap_uint<2> pad, ap_uint<9> iw, ap_uint<9> cw,
    hls::stream<PixelSums>& sums) {
#pragma HLS INLINE off
#pragma HLS ARRAY_PARTITION variable=wc complete dim=1
#pragma HLS ARRAY_PARTITION variable=bias complete
#pragma HLS ARRAY_PARTITION variable=row_base complete
#pragma HLS ARRAY_PARTITION variable=row_valid complete
    ap_int<32> accum[PE];
#pragma HLS ARRAY_PARTITION variable=accum complete
    for(unsigned x=0;x<cw;++x) {
        for(unsigned p=0;p<PE;++p) {
#pragma HLS UNROLL
            accum[p]=bias[p];
        }
            // One explicit scan counter avoids nested-loop flattening's
            // long reset/select feedback through the running weight index.
            ap_uint<4> ky=0,kx=0;
            ap_uint<6> g=0;
            ap_int<11> x_origin=int(x*stride)-int(pad);
            for(ap_uint<10> z=0;z<kw;++z) {
#pragma HLS PIPELINE II=1
#pragma HLS LOOP_TRIPCOUNT min=16 max=512
                ap_int<11> sx=x_origin+ap_int<5>(kx);
                bool valid=row_valid[ky] && sx>=0 && sx<int(iw);
                ap_uint<15> column_offset=ap_uint<9>(sx)*cg;
                ap_uint<15> address=ap_uint<15>(row_base[ky])+column_offset+g;
                ap_uint<64> v=valid ? rows[address] : ap_uint<64>(0);
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
                ap_uint<6> next_group=g+1;
                ap_uint<4> next_column=kx+1;
                bool end_group=next_group==cg;
                bool end_row=end_group && next_column==k;
                g=end_group ? ap_uint<6>(0):next_group;
                if(end_group)kx=end_row ? ap_uint<4>(0):next_column;
                if(end_row)++ky;
            }
        PixelSums packet=0;
        for(unsigned p=0;p<PE;++p) {
#pragma HLS UNROLL
            packet.range(32*p+31,32*p)=ap_uint<32>(accum[p]);
        }
        sums.write(packet);
    }
}

static void emit_row(ap_uint<64>*mem, unsigned dst, unsigned oc,
    ap_uint<9> y, ap_uint<9> cw, ap_uint<9> ow, ap_uint<10> cout,
    bool relu, bool pool, const ap_int<32> mult[PE],
    hls::stream<PixelSums>& sums) {
#pragma HLS INLINE off
#pragma HLS ARRAY_PARTITION variable=mult complete
    // Even rows overwrite every used entry before an odd row reads it.
    // Local persistent state avoids a caller-to-consumer PIPO dependency.
    static ap_int<8> top[256][PE];
#pragma HLS ARRAY_PARTITION variable=top complete dim=2
#pragma HLS BIND_STORAGE variable=top type=ram_2p impl=lutram
    ap_int<8> left[PE],q[PE];
#pragma HLS ARRAY_PARTITION variable=left complete
#pragma HLS ARRAY_PARTITION variable=q complete
    ap_uint<7> og=cout/8;
    ap_uint<16> out_row_words=unsigned(ow)*unsigned(og);
    for(unsigned x=0;x<cw;++x) {
        PixelSums packet=sums.read();
        // Keep exactly four requantizers and the original Q30 rounding.
        for(unsigned p=0;p<PE;++p) {
#pragma HLS PIPELINE II=1
#pragma HLS UNROLL factor=4
            ap_int<32> value=packet.range(32*p+31,32*p);
            q[p]=requant(value,mult[p],relu);
        }
        bool emit=!pool;
        unsigned oy=y,ox=x;
        if(pool) {
            emit=(y&1) && (x&1);
            oy=y/2;ox=x/2;
            for(unsigned p=0;p<PE;++p) {
#pragma HLS UNROLL
                if(!(y&1)) top[x][p]=q[p];
                else if(!(x&1)) left[p]=q[p];
                else q[p]=average4(top[x-1][p],top[x][p],left[p],q[p]);
            }
        }
        if(emit) {
            ap_uint<25> row_offset=ap_uint<9>(oy)*out_row_words;
            ap_uint<16> column_offset=ap_uint<9>(ox)*og;
            unsigned base=dst+unsigned(row_offset)+unsigned(column_offset)+oc/8;
            for(unsigned group=0;group<PE/8;++group) {
#pragma HLS PIPELINE II=1
                ap_uint<64> out=0;
                for(unsigned s=0;s<SIMD;++s) {
#pragma HLS UNROLL
                    out.range(8*s+7,8*s)=ap_uint<8>(q[group*8+s]);
                }
                if(oc+group*8<cout)mem[base+group]=out;
            }
        }
    }
}

static void overlap_row(ap_uint<64>*mem,unsigned dst,unsigned oc,
    ap_uint<9> y,ap_uint<9> iw,ap_uint<9> cw,ap_uint<9> ow,ap_uint<10> cout,
    ap_uint<6> cg,ap_uint<10> kw,ap_uint<4> k,ap_uint<2> stride,
    ap_uint<2> pad,bool relu,bool pool,
    const ap_uint<64> rows[8192],const ap_uint<64> wc[PE][MAX_KWORDS],
    const ap_int<32> bias[PE],const ap_int<32> mult[PE],
    const ap_uint<14> row_base[8],const bool row_valid[8]) {
#pragma HLS INLINE off
#pragma HLS DATAFLOW
    hls::stream<PixelSums> sums("pixel_sums");
#pragma HLS STREAM variable=sums depth=4
#pragma HLS BIND_STORAGE variable=sums type=fifo impl=lutram
    mac_row(rows,wc,bias,row_base,row_valid,cg,kw,k,stride,pad,iw,cw,sums);
    emit_row(mem,dst,oc,y,cw,ow,cout,relu,pool,mult,sums);
}

static void conv_layer(ap_uint<64>*mem,unsigned src,unsigned dst,unsigned wo,
    unsigned bo,unsigned mo,ap_uint<9> ih,ap_uint<9> iw,ap_uint<9> cin,ap_uint<10> cout,
    ap_uint<4> k,ap_uint<2> stride,ap_uint<2> pad,bool relu,bool pool,ap_uint<9> oh,ap_uint<9> ow) {
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
    ap_int<32> bias[PE], mult[PE];
#pragma HLS ARRAY_PARTITION variable=wc complete dim=1
#pragma HLS BIND_STORAGE variable=wc type=ram_1p impl=bram
#pragma HLS BIND_STORAGE variable=rows type=ram_1p impl=bram
#pragma HLS ARRAY_PARTITION variable=bias complete
#pragma HLS ARRAY_PARTITION variable=mult complete
    // Scalar addresses remain 32-bit word offsets; the AXI master uses a
    // 32-bit byte address on Zynq-7020. Bound shape products before adding
    // DDR bases, rather than synthesizing 32x32 multiplies and 64-bit adds.
    ap_uint<6> cg=(unsigned(cin)+7)/8;
    ap_uint<10> kw=unsigned(k)*unsigned(k)*unsigned(cg);
    ap_uint<14> row_words=unsigned(iw)*unsigned(cg);
    unsigned ch=(unsigned(ih)+2*unsigned(pad)-unsigned(k))/unsigned(stride)+1;
    unsigned cw=(unsigned(iw)+2*unsigned(pad)-unsigned(k))/unsigned(stride)+1;
    for(unsigned oc=0;oc<cout;oc+=PE) {
        for(unsigned p=0;p<PE;++p) {
            bias[p]=oc+p<cout ? ap_int<32>(mem[bo+oc+p]) : ap_int<32>(0);
            mult[p]=oc+p<cout ? ap_int<32>(mem[mo+oc+p]) : ap_int<32>(0);
            unsigned weight_base=wo+(oc+p)*unsigned(kw);
            for(unsigned z=0;z<kw;++z) {
#pragma HLS PIPELINE II=1
#pragma HLS LOOP_TRIPCOUNT min=16 max=512
                wc[p][z]=oc+p<cout ? mem[weight_base+z] : ap_uint<64>(0);
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
                unsigned base=slot*unsigned(row_words);
                row_base[ky]=base;
                if(tags[slot]!=sy) {
                    ap_uint<23> row_offset=ap_uint<9>(sy)*row_words;
                    unsigned source_row=src+unsigned(row_offset);
                    for(unsigned r=0;r<row_words;++r) {
#pragma HLS PIPELINE II=1
                        rows[base+r]=mem[source_row+r];
                    }
                    tags[slot]=sy;
                }
            } else row_base[ky]=0;
          }
          overlap_row(mem,dst,oc,y,iw,cw,ow,cout,cg,kw,k,stride,pad,relu,pool,
                      rows,wc,bias,mult,row_base,row_valid);
        }
    }
    (void)oh;
}

static void resize_layer(ap_uint<64>*mem,unsigned src,unsigned dst,unsigned coords,
    ap_uint<9> ih,ap_uint<9> iw,ap_uint<9> channels,ap_uint<9> oh,ap_uint<9> ow) {
#pragma HLS INLINE off
    ap_uint<6> groups=channels/8;
    ap_uint<14> row_words=iw*groups;
    ap_uint<14> output_row_words=ow*groups;
    for(unsigned y=0;y<oh;++y) {
        ap_uint<64> cy=mem[coords+y];
        ap_uint<9> y0=cy.range(15,0), y1=cy.range(31,16);
        ap_uint<16> fy=cy.range(47,32);
        unsigned source_row0=src+unsigned(y0*row_words);
        unsigned source_row1=src+unsigned(y1*row_words);
        unsigned output_row=dst+unsigned(ap_uint<9>(y)*output_row_words);
        for(unsigned x=0;x<ow;++x) {
            ap_uint<64> cx=mem[coords+oh+x];
            ap_uint<9> x0=cx.range(15,0), x1=cx.range(31,16);
            ap_uint<16> fx=cx.range(47,32);
            unsigned a0=source_row0+unsigned(x0*groups);
            unsigned a1=source_row0+unsigned(x1*groups);
            unsigned b0=source_row1+unsigned(x0*groups);
            unsigned b1=source_row1+unsigned(x1*groups);
            unsigned output_pixel=output_row+unsigned(ap_uint<9>(x)*groups);
            for(unsigned g=0;g<groups;++g) {
                ap_uint<64> aa=mem[a0+g];
                ap_uint<64> ab=mem[a1+g];
                ap_uint<64> ba=mem[b0+g];
                ap_uint<64> bb=mem[b1+g];
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
                mem[output_pixel+g]=out;
            }
        }
    }
    (void)ih;
}

// Check already range-bounded dimensions in a separate scheduled function.
// Avoid a chain of full 32-bit multiplications feeding the top-level FSM.
static unsigned validate_conv_shape(ap_uint<9> ih,ap_uint<9> iw,ap_uint<9> cin,
    ap_uint<4> k,ap_uint<2> stride,ap_uint<2> pad,bool pool,ap_uint<9> oh,ap_uint<9> ow) {
#pragma HLS INLINE off
    ap_uint<6> groups=(unsigned(cin)+7U)/8U;
    ap_uint<8> square=k*k;
    ap_uint<14> kernel_words=square*groups;
    ap_uint<14> row_words=iw*groups;
    ap_uint<18> cache_words=k*row_words;
    ap_uint<10> ph=unsigned(ih)+2U*unsigned(pad);
    ap_uint<10> pw=unsigned(iw)+2U*unsigned(pad);
    if(kernel_words>MAX_KWORDS || cache_words>8192U || ph<k || pw<k)return 3;
    ap_uint<10> nh=ph-k,nw=pw-k;
    // stride is checked to be 1 or 2 before entry.
    ap_uint<10> ch=(stride==2 ? (nh>>1):nh)+1U;
    ap_uint<10> cw=(stride==2 ? (nw>>1):nw)+1U;
    ap_uint<10> expected_h=pool ? (ch>>1):ch;
    ap_uint<10> expected_w=pool ? (cw>>1):cw;
    if(ch>256U || cw>256U || oh!=expected_h || ow!=expected_w)return 4;
    return 0;
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
       !stride || stride>2 || pad>2) return 3;
    unsigned shape_status=validate_conv_shape(ih,iw,cin,kernel,stride,pad,pool!=0,oh,ow);
    if(shape_status)return shape_status;
    conv_layer(mem,src,dst,weights,biases,multipliers,ih,iw,cin,cout,kernel,stride,pad,relu!=0,pool!=0,oh,ow);
    return 0;
}
