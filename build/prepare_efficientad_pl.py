"""Verify the tracked deployment bundle, then prepare ignored editable workdirs."""
from pathlib import Path
import argparse,hashlib,json,shutil,zipfile

ROOT=Path(__file__).resolve().parents[1]

def prepare(output):
    output=output.resolve()
    allowed=(ROOT/'build/work').resolve()
    if output!=allowed and allowed not in output.parents:
        raise ValueError('Output must remain under this repository build/work')
    archive=ROOT/'board/efficientad_pl/efficientad_full_pl_packed.zip'
    manifest=json.loads((archive.parent/'bundle_manifest.json').read_text(encoding='utf-8'))
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    if digest!=manifest['sha256']:
        raise ValueError('Deployment archive hash mismatch')
    output.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:
            raise ValueError('Invalid ZIP entry CRC')
        for entry in z.infolist():
            target=(output/entry.filename).resolve()
            if output not in target.parents:
                raise ValueError('ZIP entry escaped output directory')
            if not entry.filename.startswith('efficientad_full_pl_packed/'):
                raise ValueError('Unexpected bundle root')
        z.extractall(output)
    source=ROOT/'src/efficientad_pl'
    for version in ('efficientad_full_pl','efficientad_full_pl_opt','efficientad_full_pl_packed'):
        shutil.copytree(source/version,output/version,dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    latest=output/'efficientad_full_pl_packed'
    common=('ea_model_data.h','ea_expected.h','engine_tests.bin','cache_tests.bin',
            'packed_tests.bin','ps_config.tcl','ps7_init.tcl')
    for version in ('efficientad_full_pl','efficientad_full_pl_opt'):
        dest=output/version/'generated'
        dest.mkdir(parents=True,exist_ok=True)
        for name in common:
            shutil.copy2(latest/'generated'/name,dest/name)
        runtime=output/version/'runtime'
        if not (runtime/'lscript.ld').exists():
            shutil.copy2(latest/'runtime/lscript.ld',runtime/'lscript.ld')
    # Vitis imports the editable current source, alongside the frozen parameters.
    for name in ('main.c','ea_score.h','lscript.ld'):
        shutil.copy2(latest/'runtime'/name,latest/'app_sources'/name)
    print('Verified archive:',digest)
    print('Prepared:',latest)
    print('Prebuilt firmware verified on two images; hardware is not programmed by this command.')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'build/work/efficientad_pl')
    prepare(parser.parse_args().output)
