"""합성(가짜) 테스트 데이터 생성기.

사내 네트워크 경로 없이도 프로그램 전체 워크플로(스캔→매칭→Excel)를 실행/검증할 수 있도록
문서 스펙과 동일한 폴더 구조 + 파일명 + INI/KLA info 를 만든다.

생성되는 layer:
  1. LYA4_재리뷰  -> Camtek 파일명형(좌표가 파일명에 포함)
  2. LYB4_재리뷰   -> Camtek INI형(ColorImageGrabingInfo.ini section 으로 좌표 산출)
  3. LYA3        -> KLA형(.jpg + .001 info + .pass)
  4. LYB3         -> Camtek 파일명형

기준/비교 layer 의 좌표를 허용 오차 내로 맞춰 실제 매칭이 보이도록 구성한다.

사용:
  python -m tools.make_sample_data [출력폴더]
출력폴더 미지정 시 output workspace 아래 sample_source/ 에 생성한다.
"""

from __future__ import annotations

import argparse
import hashlib
import random
from pathlib import Path

from PIL import Image, ImageDraw

from app import config

# 문서 KLA 예시의 DiePitchY
KLA_DIE_PITCH = "4.4905301000e+004"
KLA_DIE_PITCH_Y = 44905.301

LOT_NAME = "204. DEVAINT.226 (PKG)"
WAFERS = ["00MHE105XYF6", "00MHE106XYC5"]

# 기준 defect 정의: (col, row, x, y, defect_name)
BASE_DEFECTS = [
    (3, 3, 5000.0, 6000.0, "Over Sized Bump"),
    (4, 5, 15055.0, 15722.0, "Particle"),
    (4, 4, 24270.0, 16328.0, "Over Sized Bump"),
    (3, 4, 30000.0, 8000.0, "Scratch"),
]

# layer 정의: (폴더명, 방식)
LAYERS = [
    ("1. LYA4_재리뷰", "camtek_name"),
    ("2. LYB4_재리뷰", "camtek_ini"),
    ("3. LYA3", "kla"),
    ("4. LYB3", "camtek_name"),
]

_COLORS = [(40, 70, 120), (90, 40, 110), (30, 100, 90), (120, 80, 30)]


def _stable_seed(*parts: object) -> int:
    """프로세스 간 재현 가능한 결정적 시드(파이썬 hash() 랜덤화 회피)."""
    digest = hashlib.md5("|".join(map(str, parts)).encode("utf-8")).digest()
    return int.from_bytes(digest[:4], "big")


def _make_image(path: Path, label: str, seed: int) -> None:
    rnd = random.Random(seed)
    color = _COLORS[seed % len(_COLORS)]
    img = Image.new("RGB", (320, 320), color=(18, 22, 34))
    draw = ImageDraw.Draw(img)
    # 중앙에 가짜 defect blob (중앙 10% 썸네일에서 보이도록)
    cx, cy = 160, 160
    for _ in range(60):
        x = cx + int(rnd.gauss(0, 12))
        y = cy + int(rnd.gauss(0, 12))
        r = rnd.randint(1, 4)
        draw.ellipse([x - r, y - r, x + r, y + r], fill=color)
    draw.rectangle([0, 0, 319, 319], outline=(30, 144, 255), width=2)
    draw.text((6, 6), label, fill=(120, 200, 255))
    img.save(path, format="JPEG", quality=80)


def _jitter(x: float, y: float, seed: int) -> tuple[float, float]:
    """허용 오차(100) 이내로 좌표를 흔들어 매칭이 성립하게 한다."""
    rnd = random.Random(seed)
    return x + rnd.uniform(-30, 30), y + rnd.uniform(-30, 30)


def _gen_camtek_name(folder: Path, layer_tag: str, wafer: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for i, (col, row, bx, by, name) in enumerate(BASE_DEFECTS):
        x, y = _jitter(bx, by, _stable_seed(layer_tag, wafer, i))
        fname = (
            f"R_DEVA_LIVE_{layer_tag}_PKG_{layer_tag}_{wafer}_"
            f"{col}_{row}_{x:.6f}_{y:.6f}_{name}.jpg"
        )
        _make_image(folder / fname, f"{layer_tag}\n{col},{row}\n{int(x)},{int(y)}", i + 1)


def _gen_camtek_ini(folder: Path, layer_tag: str, wafer: str) -> None:
    """Camtek INI형: 원본 section-key 이름 이미지 + ColorImageGrabingInfo.ini.

    원하는 col_row_x_y 에서 INI 의 Col/Row/X/Y 를 역산한다:
      Col = col + 2 ; Row = 7 - row
      X   = x + Col * PitchX ; Y = y + Row * PitchY
    """
    folder.mkdir(parents=True, exist_ok=True)
    ini_lines: list[str] = []
    for i, (col, row, bx, by, name) in enumerate(BASE_DEFECTS):
        x, y = _jitter(bx, by, _stable_seed(layer_tag, wafer, i, "ini"))
        col_ini = col + config.CAMTEK_COL_OFFSET
        row_ini = config.CAMTEK_ROW_BASE - row
        X = x + col_ini * config.CAMTEK_PITCH_X
        Y = y + row_ini * config.CAMTEK_PITCH_Y
        orig = f"{int(X)}.{int(Y)}.c.{1000000 + i}.1"
        img_name = f"{orig}.jpg"
        _make_image(folder / img_name, f"{layer_tag} INI\n{col},{row}", i + 10)
        ini_lines += [
            f"[{orig}.jpeg]",
            f"X={X:.9f}",
            f"Y={Y:.9f}",
            "StageZ=74818.4",
            f"FaultX={X:.9f}",
            f"FaultY={Y:.9f}",
            "PixelSizeX=0.461737006902695",
            "Mag=7.5",
            f"Col={col_ini}",
            f"Row={row_ini}",
            "",
        ]
    (folder / "1. ColorImageGrabingInfo.ini").write_text(
        "\n".join(ini_lines), encoding="utf-8"
    )


def _gen_kla(folder: Path, layer_tag: str, wafer: str) -> None:
    """KLA형: .jpg + .001 info(TiffFileName/DiePitch/DefectList) + .pass.

    원하는 col_row_x_y 에서 KLA 값을 역산한다:
      XINDEX = col - 3 ; YINDEX = row - 3
      XREL   = x ; YREL = DiePitchY - y
    """
    folder.mkdir(parents=True, exist_ok=True)
    info_lines = [
        "FileVersion 1 2;",
        f"DiePitch 3.7247898000e+004 {KLA_DIE_PITCH};",
        "SampleType WAFER;",
    ]
    for i, (col, row, bx, by, name) in enumerate(BASE_DEFECTS):
        x, y = _jitter(bx, by, _stable_seed(layer_tag, wafer, i, "kla"))
        xindex = col - config.kla_zero_x()
        yindex = row - config.kla_zero_y()
        xrel = x
        yrel = KLA_DIE_PITCH_Y - y
        jpg = f"{wafer}_0_{i}_{i + 5}_1.jpg"
        _make_image(folder / jpg, f"{layer_tag} KLA\n{col},{row}", i + 20)
        info_lines.append(f"TiffFileName {jpg};")
        info_lines.append("DefectList")
        # DEFECTID X Y XREL YREL XINDEX YINDEX XSIZE YSIZE ...
        info_lines.append(
            f" {i + 1} -100.0 200.0 {xrel:.3f} {yrel:.3f} {xindex} {yindex} "
            "5.2 3.9 20.28 5.2 23 3 1 0 2 2 0 1449 0 1 1 1 0;"
        )
    uuid = "2e39685b-23d5-46c6-9172-7ff58fb91c85"
    (folder / f"{uuid}_DEVA_{wafer}.001").write_text(
        "\n".join(info_lines), encoding="utf-8"
    )
    (folder / f"{uuid}_DEVA_{wafer}.pass").write_text("ignore me", encoding="utf-8")


def generate(target_root: Path) -> Path:
    """LOT 폴더를 생성하고 그 경로를 반환."""
    lot = target_root / LOT_NAME
    for folder_name, kind in LAYERS:
        layer_tag = folder_name.split(".", 1)[-1].strip().replace("_재리뷰", "")
        for wafer in WAFERS:
            wafer_dir = lot / folder_name / wafer
            if kind == "camtek_name":
                _gen_camtek_name(wafer_dir, layer_tag, wafer)
            elif kind == "camtek_ini":
                _gen_camtek_ini(wafer_dir, layer_tag, wafer)
            elif kind == "kla":
                _gen_kla(wafer_dir, layer_tag, wafer)
    return lot


def main() -> None:
    parser = argparse.ArgumentParser(description="합성 테스트 데이터 생성기")
    parser.add_argument(
        "output",
        nargs="?",
        default=None,
        help="출력 폴더(미지정 시 workspace/sample_source)",
    )
    args = parser.parse_args()

    if args.output:
        root = Path(args.output)
    else:
        root = config.default_workspace() / "sample_source"
    root.mkdir(parents=True, exist_ok=True)
    lot = generate(root)
    print(f"샘플 LOT 생성 완료: {lot}")


if __name__ == "__main__":
    main()
