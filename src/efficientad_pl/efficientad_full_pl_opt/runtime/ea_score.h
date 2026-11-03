#ifndef EA_SCORE_H
#define EA_SCORE_H
#include <stdint.h>
#ifndef EA_SCORE_API
#define EA_SCORE_API static
#endif
static float ea_padded(const float *map,unsigned y,unsigned x) {
    if(y<4U || y>=60U || x<4U || x>=60U) return 0.0f;
    return map[(y-4U)*56U+x-4U];
}
EA_SCORE_API float ea_compute_score(const int8_t *teacher,const int8_t *student,
    const int8_t *ae,float ts,float ss,float as,const float *mean,const float *std,
    const float *q,float *fused) {
    unsigned p,c,y,x;
    float best=-3.402823466e38f;
    for(p=0;p<56U*56U;++p) {
        double st_sum=0.0,ae_sum=0.0;
        for(c=0;c<384U;++c) {
            float t=((float)teacher[p*384U+c]*ts-mean[c])/std[c];
            float st=t-(float)student[p*768U+c]*ss;
            float ad=(float)ae[p*384U+c]*as-(float)student[p*768U+384U+c]*ss;
            float st2=st*st,ae2=ad*ad;
            st_sum+=(double)st2;ae_sum+=(double)ae2;
        }
        float st=(float)(st_sum/384.0), ad=(float)(ae_sum/384.0);
        st=0.1f*(st-q[0])/(q[1]-q[0]);
        ad=0.1f*(ad-q[2])/(q[3]-q[2]);
        fused[p]=0.5f*st+0.5f*ad;
    }
    // pad(4), resize 64->256 with bilinear align_corners=False, then max.
    for(y=0;y<256U;++y) {
        float sy=((float)y+0.5f)*0.25f-0.5f;
        if(sy<0.0f)sy=0.0f;
        if(sy>63.0f)sy=63.0f;
        unsigned y0=(unsigned)sy,y1=y0<63U?y0+1U:y0; float fy=sy-(float)y0;
        for(x=0;x<256U;++x) {
            float sx=((float)x+0.5f)*0.25f-0.5f;
            if(sx<0.0f)sx=0.0f;
            if(sx>63.0f)sx=63.0f;
            unsigned x0=(unsigned)sx,x1=x0<63U?x0+1U:x0; float fx=sx-(float)x0;
            float top=(1.0f-fx)*ea_padded(fused,y0,x0)+fx*ea_padded(fused,y0,x1);
            float bot=(1.0f-fx)*ea_padded(fused,y1,x0)+fx*ea_padded(fused,y1,x1);
            float value=(1.0f-fy)*top+fy*bot;
            if(value>best)best=value;
        }
    }
    return best;
}
#endif
