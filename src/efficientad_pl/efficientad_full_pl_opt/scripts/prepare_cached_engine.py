from pathlib import Path
r=Path(__file__).resolve().parents[1]
s=(r.parent/'efficientad_full_pl/hls/efficientad_engine.cpp').read_text()
s=s.replace('ap_uint<64> patch[MAX_KWORDS];','''// Circular k-row cache: <=8192 words for every frozen model layer.
    ap_uint<64> rows[8192];
    int tags[8];
    ap_uint<14> row_base[8];
    bool row_valid[8];
#pragma HLS ARRAY_PARTITION variable=tags complete
#pragma HLS ARRAY_PARTITION variable=row_base complete
#pragma HLS ARRAY_PARTITION variable=row_valid complete''')
s=s.replace('#pragma HLS BIND_STORAGE variable=patch type=ram_1p impl=bram', '#pragma HLS BIND_STORAGE variable=rows type=ram_1p impl=bram')
start=s.index('        for(unsigned y=0;y<ch;++y)')
end=s.index('            // One shared requantizer;',start)
s=s[:start]+'''        for(unsigned ky=0;ky<8;++ky) tags[ky]=-1000;
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
                    for(unsigned p=0;p<PE;++p) {
#pragma HLS UNROLL
                        ap_int<8> wv[SIMD];
#pragma HLS ARRAY_PARTITION variable=wv complete
                        ap_uint<64> w=wc[p][z];
                        for(unsigned a=0;a<SIMD;++a) {
#pragma HLS UNROLL
                            wv[a]=w.range(8*a+7,8*a);
                        }
                        accum[p]+=mac<SIMD>(ap_int<32>(0),wv,iv,ap_resource_dsp());
                    }
                    ++z;
                }
              }
            }
'''+s[end:]
s=s.replace('ih+2*pad<kernel || iw+2*pad<kernel)', 'ih+2*pad<kernel || iw+2*pad<kernel || kernel*iw*((cin+7)/8)>8192)')
(r/'hls/efficientad_engine.cpp').write_text(s)
