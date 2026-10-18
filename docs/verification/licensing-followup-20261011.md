# TwinPulse 라이선스 잔여와 배포 출처 검증

## 적용 결과

2026-10-11 Baseline v1.0.423. 사용자의 “미해결과 이후 작업을 순서대로 적용” 요청은 바로 앞 라이선스 적용 기록의 잔여 세 항목부터 처리했다. Isaac 권리 범위 확인 → 실제 의존성 목록과 원고지 검사 → 기존 배포 경로의 공개 콘텐츠 점검 순서다. **반복 가능한 오프라인 점검은 연결됐지만, 공개 권리·개인정보의 모든 개별 판단이나 전체 제품 데모가 완료된 것은 아니다.**

변경 파일은 `scripts/audit_release_provenance.py`, `tests/integration/test_release_provenance.py`, 기존 `scripts/build_offline_release.ps1`, `docs/RELEASE_PROVENANCE.md`, `docs/LICENSING.md`, `THIRD_PARTY_NOTICES.md`, README/AGENTS와 Baseline/Memory/progress다. 기존 Apache 원문/NOTICE/CITATION 의미와 자체 소스 헤더를 유지했다. 새 유료 호출, Cloud, Isaac 실행, SSH/serial/모터, 설치, 배포, 공개 전환, commit/push는 0이다. native 예약은 PAUSED를 유지했다.

## Isaac과 변환 자산

NVIDIA의 [공식 라이선스 안내](https://docs.isaacsim.omniverse.nvidia.com/latest/common/licenses-isaac-sim.html)는 공개 Isaac 소스와 별도 Kit/모델/텍스처 조건을 구분한다. [공식 FAQ](https://docs.isaacsim.omniverse.nvidia.com/latest/common/license-faq.html)는 내부 실행/자체 코드·USD 결과 전달과 runtime 재배포/서비스를 구분한다. 따라서 TwinPulse의 Apache 선언이 Isaac 설치본 전체에 적용된다고 쓰지 않았다.

local read-only 검사: `6.0.1-rc.7+release.42383.32955d8d.gl`, URDF extension config의 `LicenseRef-NvidiaProprietary`, bundled `urdf-usd-converter` 0.1.3의 Apache-2.0 METADATA와 원 LICENSE를 확인했다. 변환 layer의 creator와 일치한다. 이 사실은 **도구의 선언**이지 모든 입력·결과물 권리의 포괄 승인으로 사용하지 않는다. [최종 inventory](../../outputs/licensing-20261011/followup-v423/final-inventory.json)에 installed 상대 경로/원문 SHA와 ROBOTIS 원 URDF/mesh 5개·변환 USD 9개 SHA를 기록했다. 실행 가능한 importer/Kit/Isaac 런타임은 패키지에 포함하지 않았다.

## 의존성 실제 목록

| 대상 | 확인 결과 |
| --- | --- |
| Node lock | source와 installed pnpm lock 원바이트/SHA 동일 |
| 설치된 Node | 101개: browser runtime 3 / Vite browser helper 1 / development 97 |
| lock에만 있는 항목 | 44개, 미설치·미배송 상태를 명시. 플랫폼 옵션/peer 여부를 모두 확정했다고 주장하지 않음 |
| browser 4개 고지 | dependency graph/설치본 원 LICENSE와 별도 배포 파일의 원바이트 포함 일치 |
| 개발 고지 미확인 | `@rolldown/binding-win32-x64-msvc` 1.2.8, `saxes` 6.0.0, `stackback` 0.0.2의 별도 이름 license/notice 파일 없음. SPDX 선언과 공개 출처를 기록했고 현 배포에 이 개발 패키지 자체는 없음 |
| Python | Core/App/Provider 실제 TOML의 이름/version/의존성과 SHA 기록 |
| Pillow | 12.3.0 wheel lock SHA 일치, MIT-CMU 선언과 bundled-library 원고지 보존. Requires-Dist 25개는 optional extras이며 base dependency로 설치/배송하지 않음 |

이는 현재 설치/배송 범위의 기계 inventory이지 표준 SBOM 적합성이나 모든 전이 라이선스의 법률 판단 PASS가 아니다. package metadata 및 외부 notice 파일은 수정하지 않았다.

## 기존 배포 경로의 검증

기존 builder가 로컬 PASS 전에 zero-network inventory/content audit를 실행하고 `provenance-audit.json`을 manifest에 포함한다. 기존 Python 3.12만 사용하며 새 설치/다운로드/배포 시스템을 추가하지 않았다. 개인 사진·raw·키·설정 파일·미확인 자료를 조용히 삭제해서 성공을 만들지 않는다. 제외 경로는 **내용을 열지 않고** 분류하며, 개인 절대 경로/잠재 키 형식의 일치는 카테고리만 저장하고 일치 문자열은 출력/보관하지 않는다. 패턴 검사는 모든 PII/secret 부재를 보증하지 않는다.

- 최종 local build: [tp-licensing-v423-final](../../outputs/licensing-20261011/followup-v423/offline-release/tp-licensing-v423-final/release-manifest.json). **manifest 700개 / 전체 25,632,946 bytes**, `REUSED_EXISTING_DIST_NOT_REBUILT`. 이 턴 새 웹/GPU 빌드를 했다고 표시하지 않았다.
- [최종 법적 파일 검사](../../outputs/licensing-20261011/followup-v423/final-legal-package-check.json): 공식 Apache SHA `cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30`, 사본 7쌍·CFF 채운 필드·현재 헤더 836개(Python 633 compile 포함)·700개 manifest SHA/bytes·법적 경로 14개·browser/Pillow 원고지 PASS. 이전 831개 가역 header 삽입 증거는 당시 기록이며 이후 의도적인 builder 변경을 원삽입만의 변경이라고 소급하지 않는다.
- 로컬 회귀 **33개 PASS**: 새 provenance 13 + 기존 license 9 + source identity 2 + packaged gate 9. 이전 31과 반복 수를 합산하지 않았다. PowerShell parser PASS. 이번 라이선스 변경에 대해 전체 제품 acceptance/신규 LLM·Isaac 회복을 주장하지 않는다.
- 실제 `-RequirePublicReview` builder 시험은 예상대로 실패(exit 1; 내부 audit exit 2)하고 [사유 report](../../outputs/licensing-20261011/followup-v423/offline-release/tp-licensing-v423-public-gate/provenance-audit.json)를 남겼다. 성공 manifest는 생성되지 않았다. 이 폴더는 인수된 배포본이 아니다. 현재 공개 gate는 기술 검사만으로 자동 승인하지 않고 별도 콘텐츠 검토를 요구한다.
- 최종 report의 **개인 절대 경로 후보 31개 파일 / 변환 자산 검토 9개 파일**은 겹친다. 40개 독립 누출이라는 뜻이 아니다. generic test literal도 후보에 포함되므로 모두 실제 개인정보라고 단정하지 않는다. USD 9개의 기존 변환 경로는 직접 확인한 공개 전 정리 대상이다.

ROBOTIS 원 LICENSE/source.json/patch SHA는 앞선 기록과 동일하다: `ac8793d277f1a08231d10e1b2ebaabb0598bd5561cfc21f97648656b416d901e` / `b933a1743954410acfe3e685fa1843610404fc1fe24a331e1020a50bcb7ca359` / `fa8fa60231daf3d90f691c1e4fc88016657e56b635cddf347d6d03fe1d5446c2`. 원자산과 기존 frozen benchmark/raw/실패는 변경하지 않았다.

## 검증 중 수정한 점

초기 manifest 감사에서 파일 membership마다 전체 relative path를 반복 계산해 불필요하게 느렸다. 한 번 계산한 집합을 재사용해 실제 감사를 약 3초 내 수행하게 했고 원 초기 report는 보존했다. `tests/fixtures/*.py`를 외부 사진 dataset으로 분류하던 false positive와 명명된 web build metadata의 미분류를 수정했다. 사진/JSON/raw는 같은 test folder에서도 자동 허용하지 않는다.

초기 pnpm 제한 parser가 깊은 peer 필드를 package key로 읽어 lock 미설치를 79개로 잘못 표시했다. 정확한 2-space package key/형식 검증과 CRLF/peer 회귀를 추가한 **최종 수치는 44개**다. `first-audit.json`, `optimized-audit.json`, `complete-inventory.json` 등 중간 파일을 덮어쓰지 않았다. 최종 근거는 `final-inventory.json`과 `final-legal-package-check.json`이다. Windows sandbox Temp 접근 오류는 허용된 로컬 테스트 권한으로 재검증했고 ACL/설치/시스템 설정을 바꾸지 않았다. 일반 프로세스 CIM 조회도 sandbox에서 거부돼 우회하지 않았고 타 프로세스를 종료하지 않았다.

## 정확한 잔여 순서

1. 공개 배포 직전: USD 9개의 실제 resource closure/입력·변환 권리 검토, 개인 경로가 제거된 **새 공개용 사본**과 새 SHA 인수. pinned 원본은 보존한다. 후보 31개의 문맥별 review와 실제 공개할 사진·리포트의 개별 권리/PII 확인도 필요하다. 개발 도구를 향후 묶어 배포한다면 현재 별도 원고지 없는 3개를 추가 확인한다.
2. 제품 구현: 범용 `warehouse.rack`/`warehouse.pallet_stack` → semantic grammar/지지 geometry 연결. 현재 라이선스 턴이 이를 해결했다고 기록하지 않았다.
3. 유효한 새 실제 시험 승인 범위에서 P2 실패 영향 범위 인수/C반복, 일반 LLM chat edit의 preview/apply/cancel/replan, loop·이상주입·독립 품질 검증.
4. 로컬 전체 성공 뒤 Cloud/현장 안전 승인된 로봇/영상/공개 재현/제출을 기존 계획 순서로 진행한다. 남은 잔액을 새 유료 호출 승인으로 간주하지 않는다.

필수 Apache 고지와 자발적 설계 출처 요청의 구분은 그대로다. 공개 준비 점검은 TwinPulse 재사용에 추가 라이선스 조건을 붙이는 것이 아니며, 모든 AI의 준수/영구적인 출처 보존이나 로봇 전원만 켜면 전체 데모 완료를 보장하지 않는다.
