# 사진 생성 실제 검사 및 계약 보완 — 2026-10-07 / v318

후속 v319: 명시 고정1.1 응답→실제 제품/Isaac 연결을 인수하면서 geometry roundtrip 해시 결함을 수정했다. 실제 모델 추가호출0, 본 문서의 실제 사진 실패는 유지한다. [현재 제품 연결·별도 미검증](photo-compact-product-connection-20261007.md).

## 결론

사용자가 방 사진의 기존 Nebius Gemma/Nemotron 전송과 최대3회 호출을 명시 승인한 뒤 **정확히3회 요청**했다. 사진 관측은 정상, 첫 계획은 API 문법 거절, 수정 후 계획은 완전한 JSON이지만 객체/근거 계약 위반으로 거절했다. **유효한 사진 장면 생성0; 새 Isaac Build/Run0; 로봇 접속/배포/센서/모터0.** 실제 오류를 보완했지만 후속 `photo-layout-1.1`은 오프라인 검증뿐이며 제품 기본값은 유지한다. H5/H6/C3–C6 PARTIAL, whole_demo_ready=false.

이번에 보낸 자료는 기존 P01 원본 방 사진(223473bytes, SHA256 `ce2093de14a799489b8b35fa25ee46dbf1a2834c67914194575426255c285eb8`)이다. 중국어 답변 화면이나 다른 새 첨부 이미지를 보내지 않았다. 기존 검토 inventory24개를 쓰는 **assisted** 검사이며 순수 사진 인식 인수가 아니다.

## 실제 요청3회와 정확한 실패 원인

| 요청 | 원본 식별자 | 실제 결과 |
|---|---|---|
| Gemma 관측 | ccdf7da9d6c845dc8bbdf625efd2d918 | HTTP200/stop, stage31.422s, prompt452/completion1073, 관측 계약 통과 |
| Nano 계획1 | 4ef5001807c54921b5d931417aedbbdc | HTTP400, `Grammar error: Unimplemented keys: ["uniqueItems"]`; 모델 출력 생성 성공 아님 |
| Nano 수정 계획 | 8ff72325ead0458e95158a5f9d38a334 | HTTP200/stop, planner12.141s, prompt2406/completion3450. 객체14개만 반환하고 관측에 없는4개 ID를 시각근거로 써 거절 |

관측에 없는 근거는 `underdesk_bag_1`, `floor_fan_1`, `window_blind_1`, `top_storage_1`이다. 검토 inventory의24개 고정 ID/category 대신 작은 관측 목록으로 대체했으며, 관측에 없는 물체를 user/reviewed 근거와 혼동했다. 성공 처리·근거 ID 자동 alias 변환·누락 항목 자동 삽입은 하지 않았다. 이번 원인은 이전8000토큰 잘림과 다르다. **14개짜리 완전 응답12.141s를24개 방 복원 성능이나 전체 사진 생성 시간으로 주장하지 않는다.**

`photo-compact-r1/result.json`은 전체32.407s FAIL이고 `photo-compact-r2/result.json`은 실제 관측 재사용 후12.141s FAIL이다. 두 파일/원본 응답은 보존했다. 재사용한 관측31.422s를 두 번째 결과의 새 실행시간/새 호출수로 중복 계산하지 않는다. 해당 두 실행은 같은 입력의 진단/수정 과정이며 독립적인 matrix2회 성공 표본이 아니다.

## 실제 오류에 따른 수정

1. API가 거절한 wire schema의 `uniqueItems`만 제거했다. 로컬 참조 중복 거절은 유지한다.
2. `ReuseExactAuditedObserver`를 평가 도구에 추가했다. 완료된 같은 campaign·model·attempt와 원본 bytes/hash, 동일 사진/프롬프트/관측 schema/request hash를 모두 확인해야 기존 실제 관측을1회 재사용한다. 변경·취소·불완전·손상 자료는 거절한다. 새 fake 응답/새 관측/다른 사진 대체가 아니다. 이 명시적 재검사의 추가 repair는0으로 제한하여 새 계획1회만 보냈다. 사용자3회 제한을 넘기지 않았다. 일반 제품에는 캐시/자동 재시도 기능을 추가하지 않았다.
3. 후속 출력 계약을 `photo-layout-1.1`로 보완했다. 검토 inventory가 있으면24개 이름 모두가 필수인 고정 dictionary slot으로 출력한다. 모델이 ID/category를 바꾸거나 짧은 배열로 대체할 수 없도록 schema/local validator 양쪽에 제약을 둔다. category는 검토 원본에서 가져오며 모델 출력의 사후 추측/정규화가 아니다.
4. observation_ids는 실제 관측 ID만 enum으로 제공한다. 실제 근거가 없으면 []를 사용하고 user/reviewed 근거로 처리한다. 로컬에서도 미관측 참조를 `PHOTO_LAYOUT_UNOBSERVED_REFERENCES`와 객체 ID/잘못된 참조로 정확히 반환한다.
5. 과거1.0 배열 계약/실패 자료는 분석 가능하게 유지했다. 기존 Site2.2 저장 serialization/hash·물리 잠금·geometry/정지 기준은 바꾸지 않았다.

**1.1 고정 슬롯 schema의 실제 API 수용/모델 출력·24개 배치 성능은 아직 NOT_RUN**이다. 이번3번째 실측은 `uniqueItems` 제거 후의1.0 응답이며 이후 코드의 성공 근거가 아니다. 추가 유료 호출은 하지 않았다.

## 최종 회귀·제한

- provider **57 / 0.880s PASS**: 기존45 및 사진 계약12개 포함; 실제 미지원 grammar 키 제거/중복 로컬 거절,24개 고정 슬롯, category/추가 필드/가짜 근거 거절 포함.
- chat/reliability/exact reuse **73 / 25.062s PASS**, 고정 응답·로컬 API만. 일부 suite의 imported tests는 중복되며 고유수 합계로 주장하지 않는다.
- exact reuse 단독4 /0.059s PASS는 위73에 포함된다.
- git diff --check PASS. 기존 dirty/raw/과거 실패 보존. Web 변경 없음, 본 증분의 actual Chrome/Isaac/실물 검증 NOT_RUN.
- 옷장 위 상자·내부 옷·이불 같은 지지/부착 관계를 독립 proxy로 대체하는 한계는 남는다. 가까운 물체를 다른 region으로 밀거나 방을 키우고 물체를 누락해 성공 처리하지 않는다. 사진 복원/실측/안전 주행 인수 아님.

## 공유 비용·호출

campaign **51/60**, 미완료 dispatch0, 기존 unknown2 유지. 알려진 usage 비용+불명 전체 예약 **USD0.09513896**, 실제 청구/잔액은 미확인이다. 이번 성공 HTTP 응답2개의 토큰 가격 추정은 USD0.00133946. HTTP400의 usage가 없으므로 원래 예약 USD0.01764864를 임의 환급하지 않고 유지했다. 따라서 캠페인 증가분은 USD0.01898810(실제 청구액 아님). 남은 전체 승인 요청수9와 이번 최대3회 제한은 다른 개념이며 이번에는4번째 요청을 하지 않았다.

## 다음 순서

1. 별도 후속 제한 묶음이 승인되면1.1 같은 사진 실제 검사. 원본/가격/한 번의 수정/전체 기한 유지; 실패시 추가 무한 호출 금지.
2. 실제24개 및 근거 계약 통과 후 지역·지지/부착·scale/배치 충실도 검증 및 구현. 단순 proxy 생성 통과를 사진 복원 완료로 채점하지 않는다.
3. 검증한 생성 정책만 기존 chat/artifact/Isaac Build/current frame/Run/Stop/reload에서 actual 인수하고 기본 경로에 채택한다. 전체 matrix·실측/정합·driver/stop·실물 임무는 독립 잔여다. 사진 출력 실패는 로봇 전원으로 해결되지 않는다.

최종 `photo_layout.py` SHA256: `0b7b9d66df77ec598f538496afa1df44f4640e87e9c410b84f1b09ba830b7bc6`; 평가 도구 SHA256: `ce845bd23a054c77b8ce13aefa44cdd33509a2f0575ea847c71ed001eee86de9`. 실제 두 result.json은 각 당시 source hash를 별도로 보존한다.
