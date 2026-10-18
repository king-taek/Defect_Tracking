---
name: awesome-design-md
description: Reference library of 73 DESIGN.md design-system analyses (Linear, Vercel, Stripe, Apple, Claude, …) from VoltAgent/awesome-design-md. Use when choosing or comparing visual language — type scale, spacing, color tokens, component density, dashboard/table patterns — for the PySide6 defect comparison viewer. Read only the one or two DESIGN.md files that fit the question; never copy a brand's identity (logo, name, signature colors) into this product.
---

# awesome-design-md (참고 라이브러리)

`design-md/<브랜드>/DESIGN.md` 마다 한 회사 화면의 디자인 체계(글꼴 · 간격 · 색 토큰 · 컴포넌트 · 원칙)가 정리돼 있다.

## 이 저장소에서 쓰는 법
- 화면 규칙의 정본은 `CLAUDE.md` 와 앱의 기존 위젯 · 스타일이다. 여기 파일은 **비교 · 영감용**이며 정본을 덮어쓰지 않는다.
- 데스크톱(PySide6) 앱이라 CSS · 웹폰트 · CDN 조언은 버리고 간격 · 대비 · 정보 순서 · 밀도 원칙만 가져온다.
- 이미지 비교 · 표가 많은 업무 화면에 가까운 것부터 본다: `linear.app`, `vercel`, `sentry`, `posthog`, `raycast`, `notion` 등 (`ls design-md/` 로 전체 목록).
- 브랜드 고유 요소(로고 · 이름 · 시그니처 색)는 가져오지 않는다.

출처: https://github.com/VoltAgent/awesome-design-md (MIT, `LICENSE`)
