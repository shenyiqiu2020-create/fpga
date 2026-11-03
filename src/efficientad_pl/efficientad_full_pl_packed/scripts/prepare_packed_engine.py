from pathlib import Path
r=Path(__file__).resolve().parents[1]
s=(r.parent/'efficientad_full_pl_opt/hls/efficientad_engine.cpp').read_text()
s=s.replace('PE=16, SIMD=8','PE=32, SIMD=8')
s=s.replace('static ap_int<8> requant', '''// DSP48E1 signed 25x18 multiplication. Pack two signed INT8 weights
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

static ap_int<8> requant''')
s=s.replace('bias[p]=ap_int<32>(mem[bo+oc+p]);','bias[p]=oc+p<cout ? ap_int<32>(mem[bo+oc+p]) : ap_int<32>(0);')
s=s.replace('mult[p]=ap_int<32>(mem[mo+oc+p]);','mult[p]=oc+p<cout ? ap_int<32>(mem[mo+oc+p]) : ap_int<32>(0);')
s=s.replace('wc[p][z]=mem[wo+(oc+p)*kw+z];','wc[p][z]=oc+p<cout ? mem[wo+(oc+p)*kw+z] : ap_uint<64>(0);')
begin=s.index('                    for(unsigned p=0;p<PE;++p)',s.index('// Read cached windows'))
end=s.index('                    ++z;',begin)
s=s[:begin]+'''                    for(unsigned p=0;p<PE;p+=2) {
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
'''+s[end:]
s=s.replace('group<2;','group<PE/8;')
s=s.replace('mem[dst+(oy*ow+ox)*og+oc/8+group]=out;',
 '''if(oc+group*8<cout) mem[dst+(oy*ow+ox)*og+oc/8+group]=out;''')
s=s.replace('// One shared requantizer; avoid 16 wide multipliers in parallel.',
            '// Four shared requantizers; 32 results in eight issue cycles.')
s=s.replace('#pragma HLS PIPELINE\n                q[p]=requant',
            '#pragma HLS PIPELINE II=1\n#pragma HLS UNROLL factor=4\n                q[p]=requant')
(r/'hls/efficientad_engine.cpp').write_text(s)
