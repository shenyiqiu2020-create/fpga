from pathlib import Path
root=Path(__file__).resolve().parents[1]
s=(root.parent/'efficientad_full_pl/runtime/main.c').read_text()
s=s.replace('#define ENGINE_TIMEOUT_SECONDS 300U', '''#define ENGINE_TIMEOUT_SECONDS 300U
#ifndef EA_COMPARE_CRC
#define EA_COMPARE_CRC 0
#endif
volatile uint32_t EaProfile[4][29][5] __attribute__((aligned(64)));
volatile uint32_t EaTotals[4][8] __attribute__((aligned(64)));
static unsigned run_index, profile_op, fast_crc;
static unsigned us(XTime a,XTime b) {return (unsigned)((b-a)*1000000ULL/(XTime)(COUNTS_PER_SECOND));}
static uint32_t crc_table[256];
static void init_crc(void) {
    for(unsigned i=0;i<256;++i) {
        uint32_t c=i;for(unsigned b=0;b<8;++b)c=(c>>1)^((c&1)?0xedb88320U:0);
        crc_table[i]=c;
    }
}''')
s=s.replace('crc^=p[i];', 'if(fast_crc) {crc=(crc>>8)^crc_table[(crc^p[i])&255U];continue;}\n        crc^=p[i];')
s=s.replace('XTime begin,now;', 'XTime begin,now,cache_begin,cache_end,kernel_end;')
s=s.replace('    Xil_DCacheFlushRange((INTPTR)src,src_bytes);', '    XTime_GetTime(&cache_begin);\n    Xil_DCacheFlushRange((INTPTR)src,src_bytes);')
s=s.replace('    // m_axi base zero;', '    XTime_GetTime(&cache_end);\n    // m_axi base zero;')
s=s.replace('    if(reg_read(0x10)!=0U)', '    XTime_GetTime(&kernel_end);\n    if(reg_read(0x10)!=0U)')
s=s.replace('    Xil_DCacheInvalidateRange((INTPTR)dst,dst_bytes);', '''    Xil_DCacheInvalidateRange((INTPTR)dst,dst_bytes);
    XTime_GetTime(&now);
    EaProfile[run_index][profile_op][0]=us(begin,kernel_end);
    EaProfile[run_index][profile_op][1]=us(cache_begin,cache_end)+us(kernel_end,now);''')
s=s.replace('    for(image=0;image<2U;++image) {', '''    init_crc();
    for(run_index=0;run_index<(EA_COMPARE_CRC?4U:2U);++run_index) {
        image=run_index&1U;
        fast_crc=EA_COMPARE_CRC ? run_index>=2U : 1U;''')
s=s.replace('                if(run_op(o,src,dst)!=0)', '                profile_op=oi;\n                if(run_op(o,src,dst)!=0)')
s=s.replace('                uint32_t crc=crc_bytes(dst,bytes);', '''                XTime cb,ce;XTime_GetTime(&cb);
                uint32_t crc=crc_bytes(dst,bytes);
                XTime_GetTime(&ce);
                EaProfile[run_index][oi][2]=us(cb,ce);
                EaProfile[run_index][oi][3]=crc;
                EaProfile[run_index][oi][4]=o->crc[image];
                Xil_DCacheFlushRange((INTPTR)EaProfile,sizeof(EaProfile));''')
s=s.replace('            memcpy(saved,src,bytes);', '''            XTime cb,ce;XTime_GetTime(&cb);
            memcpy(saved,src,bytes);
            XTime_GetTime(&ce);EaTotals[run_index][5]+=us(cb,ce);''')
s=s.replace('        float score=ea_compute_score', '        XTime sb,se;XTime_GetTime(&sb);\n        float score=ea_compute_score')
s=s.replace('        float difference=score-', '        XTime_GetTime(&se);EaTotals[run_index][4]=us(sb,se);\n        float difference=score-')
s=s.replace('        EaStatus[1]=3U;status_flush();', '''        EaTotals[run_index][0]=us(start,end);
        EaTotals[run_index][6]=score_bits;
        EaTotals[run_index][7]=score>ea_threshold;
        for(unsigned i=0;i<29;++i)for(unsigned j=0;j<3;++j)EaTotals[run_index][j+1]+=EaProfile[run_index][i][j];
        Xil_DCacheFlushRange((INTPTR)EaTotals,sizeof(EaTotals));
        EaStatus[1]=3U;status_flush();''')
(root/'runtime/main.c').write_text(s)
