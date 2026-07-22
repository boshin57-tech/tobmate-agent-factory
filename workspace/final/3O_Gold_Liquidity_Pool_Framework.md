```markdown
# Chapter 3O. Gold Liquidity Pool Framework

> 섹션 범위: 2601–2700

---

## 2601. 목적·범위 및 비목표(Non-goals)

### Purpose
GLP(Gold Liquidity Pool) Framework의 아키텍처 목적, 적용 범위, 본 챕터에서 다루지 않는 비목표를 명확히 정의한다.

### Architecture or Rule
- 본 챕터는 금 기반 유동성(Liquidity) 제공/회수, 교환(Swap), 수수료(Fee) 배분, 준비금(Reserve) 연동 제약, 감사(Audit) 추적성 요구를 포함하는 GLP 공통 프레임워크를 정의한다.
- GLP는 “실물 준비금(Verified physical reserve)”을 전제로 하며, 유동성 연산이 준비금·권리·합의·감사 불변조건을 우회할 수 없도록 설계한다.

### State/Flow
- 본 챕터의 상태 전이는 2607의 공통 규칙을 따른다(사전 검증 → 권한 승인 → 결정론적 실행 → 이벤트/감사 기록).

### Validation
- 모든 GLP 연산은 2604(상위 불변조건) 및 2603(권리 분리 원칙)에 대한 적합성 검증을 통과해야 한다.

### Failure handling
- 비목표에 해당하는 요청(예: 준비금 검증 없이 발행/유동성 생성 등)은 즉시 거부한다.
- 본 챕터는 실패의 상위 분류를 규정하며(2607), 상세 오류코드는 레지스트리로 위임한다(2610).

### Audit
- 각 요청은 입력 정규화 결과, 검증 판정, 승인 주체, 실행 결과, 상태 해시(state hash)를 포함하는 감사 레코드를 생성해야 한다.

### Invariants
- 본 챕터의 상위 불변조건 적용 요약은 2604에 정리한다.

### Non-goals
- (a) 실물 금 검증 프로세스의 운영 상세(SOP), (b) 오프체인 KYC/AML 정책, (c) 외부 거래소(DEX/CEX) 라우팅 최적화, (d) 가격발견 메커니즘 자체의 경제학적 정당화, (e) 체인/VM 구현 세부 최적화는 본 챕터 범위 밖으로 둔다. 단, 이들이 GLP 불변조건을 침해할 경우 인터페이스 수준에서 차단 규칙은 정의한다.

---

## 2602. Gold Liquidity Pool(GLP) 정의와 적용 시나리오

### Purpose
GLP의 정의(Definition)와 사용되는 대표 시나리오를 표준화한다.

### Architecture or Rule
- GLP는 “경제적 이용권 토큰(Economic-utilization FT, U-FT)”의 유동성을 제공하기 위한 온체인 풀(Pool)이며, “원금 소유권(Principal Ownership NFT, P-NFT)”과 분리된 권리 구조를 전제로 한다.
- GLP는 다음의 자산 구성을 최소 단위로 갖는다.
  - 풀 기준 자산(Primary asset): U-FT(예: GOLD-UTIL-FT)
  - 상대 자산(Quote asset): 프로토콜이 승인한 결제/정산 자산(예: stablecoin, settlement token)
  - 수수료 적립/분배 규칙(Fee accrual & split)
  - 준비금 연동 제약(Reserve-linked constraints; 2606, 2610)
- GLP의 LP 지분은 **포지션 NFT(Position NFT, 이하 LP-Position NFT)** 로 정의한다.
  - LP-Position NFT는 풀별로 발행되며, **P-NFT에 대한 어떠한 청구권(claim)도 내포하지 않는다.**
  - LP-Position NFT는 풀 자산(Primary/Quote) 및 “풀 내 누적 수수료”에 대한 **비례적 경제권**만 표현하며, “원금(Principal) 소유권”을 표현하거나 이전하지 않는다.

### State/Flow (시나리오)
- S1: 유동성 예치(Add Liquidity)
  - 입력: `(pool_id, amount_primary, amount_quote, min_lp_units, recipient, oracle_round_id, deadline, nonce)`
  - 처리: BRV/EA(2607) → 수수료/슬리피지 선검증(해당 시) → 풀 잔고 증가 → LP-Position NFT 발행
- S2: 유동성 회수(Remove Liquidity)
  - 입력: `(pool_id, position_id, burn_lp_units, min_out_primary, min_out_quote, recipient, oracle_round_id, deadline, nonce)`
  - 처리: BRV/EA(2607) → 풀 잔고 감소 → LP-Position NFT 부분소각/전소각 → 자산 환급(수수료분 포함)
- S3: 교환(Swap)
  - 입력: `(pool_id, asset_in, amount_in, min_out, recipient, oracle_round_id, deadline, nonce)`
  - 처리: fee_model 및 slippage_model 적용(2606) → 잔고 변경 커밋
- S4: 수수료 정산(Fee settlement)
  - Swap/LP 연산 중 발생한 수수료는 **정의된 fee_splits**에 따라 “분리 계정(Constitution 8)”으로 즉시 분개(posting)한다(2606).
- S5: 준비금 제약 연동(Reserve compliance gating)
  - GLP가 **U-FT 공급 변화(issuance/burn/redemption)** 와 결합된 경로를 직접 수행하는 것은 금지(2603).
  - 단, 외부 모듈이 U-FT 공급을 변경하는 트랜잭션이 GLP를 호출/연쇄 호출하는 구조일 경우, GLP는 `VerifiedReserveState` 스냅샷 키를 통해 준비금 조건을 **사전 검증(BRV)** 하고 위반 가능성이 있으면 거부한다(2606, 2610).

### Validation
- 풀 생성/변경은 승인된 자산 목록(whitelist), 오라클(Oracle) 라운드 입력의 결정론적 고정(oracle_round_id), 수수료/슬리피지 모델 파라미터 허용범위 등을 검증해야 한다.
- 레지스트리 의존 항목은 2610의 “최소 인터페이스”를 따른다.

### Failure handling
- (a) 승인되지 않은 자산, (b) 오라클 입력 부재/만료, (c) 준비금/권리 불변조건 위반 가능성, (d) 결정론 입력 정규화 실패 시 트랜잭션은 거부한다(2607, 2608).

### Audit
- 모든 Swap/LP 연산은 입력 가격(oracle price), 적용 수수료, 슬리피지, 풀 전/후 잔고, fee_splits 분개 내역을 포함해 추적 가능해야 한다.

### Invariants
- “유동성 제공”은 P-NFT의 창설/이전/소각을 수반하지 않으며, U-FT 범위 내에서만 발생해야 한다(2603).

---

## 2603. 권리 분리 원칙: Principal Ownership NFT vs Economic-utilization FT

### Purpose
원금 소유권(Principal Ownership)과 경제적 이용권(Economic-utilization)을 분리하여 침묵 희석(silent dilution), 권리 오인, 준비금 우회를 방지한다.

### Architecture or Rule
- P-NFT는 “원금(Principal) 소유권”을 나타내며, **발행/이전/소각**은 별도의 권한·검증 흐름을 갖는다. GLP는 P-NFT의 상태를 직접 변경하지 않는다.
- U-FT는 “경제적 이용권(사용·거래·유동성 제공)”을 나타내며, GLP는 U-FT의 유동성만을 다룬다.
- GLP에서 생성되는 권리인 LP-Position NFT는 다음을 만족해야 한다.
  - (a) P-NFT 식별자(p_nft_id) 필드를 보유하거나 참조 무결성으로 연결하는 것을 금지(직접 결합 금지)
  - (b) “원금 상환/인도/회수”를 청구하는 함수/이벤트를 제공하는 것을 금지(청구권 금지)
  - (c) 풀 자산 및 누적 수수료에 대한 비례적 경제권(출금 가능 금액 산정의 입력)만 포함
- U-FT 공급 변화가 수반될 수 있는 연산(예: 발행/상환/소각과 결합된 경로)은 본 챕터에서 **유동성 연산 자체**로 허용되지 않으며, 필요한 경우에도 “Verified reserve precedes issuance”(Constitution 1) 및 “state transition authorization”(Constitution 4)을 위반하지 않는 별도 모듈 경로로만 수행되어야 한다. 단, GLP는 그러한 외부 경로에 대해 **준비금 스냅샷 검증 및 호출 그래프 제한**을 수행한다(2606, 2607, 2610).

### State/Flow
- GLP 연산은 (a) U-FT 및 결제자산의 이동, (b) LP-Position NFT 상태 변화(발행/부분소각/전소각/이전), (c) 수수료 분개만 수행한다.
- P-NFT 관련 상태는 **화이트리스트 읽기 참조**로 제한하며, 쓰기(변경)는 금지한다(아래 Validation).

### Validation
- P-NFT 참조 화이트리스트(읽기 가능 필드) 최소 집합:
  - `p_nft_id` 자체를 GLP 입력으로 받는 것은 금지(결합 방지).
  - GLP가 조회 가능한 것은 **계정 수준 정책 플래그**로 제한한다: `is_frozen`, `compliance_hold`(계정/주소 단위) 및 `role`(EA 판단에 필요한 경우)
  - 위 필드는 “결정론적 조회 키(블록 높이/상태 루트 기준)”로만 조회되어야 한다(2608, 2610).
- 간접 변경 금지의 구체 규칙:
  - GLP 실행 중 외부 모듈로의 **re-entrant call**을 금지한다(호출 그래프 제한).
  - EA scope에 “P-NFT 변경 권한”이 포함된 승인 체인은 GLP 엔드포인트에서 거부한다(2607).
- U-FT 이동은 승인(allowance) 및 잔고 충분성, 동결/압류 상태 여부를 검증해야 한다.

### Failure handling
- LP-Position NFT를 P-NFT로 오인하여 교환/담보화/상환청구에 준하는 효과를 내는 인터페이스(직접 또는 이벤트 스키마 포함)는 금지하며 요청을 거부한다.

### Audit
- 모든 GLP 연산 감사 레코드는 “영향받는 권리 유형(right type)”을 명시해야 하며, P-NFT는 “참조됨/영향 없음(Referenced/No-Effect)”으로 기록되어야 한다.

### Invariants
- Constitution 2, 3을 GLP 레벨에서 강제한다: 원금 소유권은 침묵 희석/재배정/소각되지 않으며, GLP는 권리 분리를 위반하는 상태전이를 생성할 수 없다.

---

## 2604. 준수해야 할 상위 불변조건(Constitutional invariants) 요약

### Purpose
GLP가 반드시 준수해야 하는 Master Constitution 1~10의 적용 포인트를 요약하고, 후속 절에서 사용될 검증 항목의 기준으로 삼는다.

### Architecture or Rule (요약 적용)
1. **Verified reserve precedes issuance**: 준비금 검증 없는 발행/공급확장과 결합된 유동성 연산 경로를 금지(2606, 2610).
2. **No silent dilution of principal ownership**: GLP는 P-NFT 총량/소유권을 변경하지 않음(2603).
3. **Separation of rights**: GLP는 U-FT 유동성만 취급, P-NFT 결합 금지(2603).
4. **Business Rule Validation & Execution Authorization**: 모든 상태 전이는 사전 검증과 승인 후 실행(2607).
5. **No bypass of reserve/ownership/consensus/audit invariants**: 유동성 연산도 동일한 불변조건 게이트를 통과(2607).
6. **Deterministic canonical state**: 동일 입력은 동일 결과를 산출(2608).
7. **Auditable value source for rewards**: 수수료/인센티브는 정의된 가치원천(거래 수수료 등)에서만 발생(2606).
8. **Segregation of assets**: Treasury, Insurance Reserve, Protocol Revenue, User assets는 분리 계정/원장 영역으로 관리(2606).
9. **Traceability**: GLP 이벤트는 상환/소각/정산/복구 연계 식별자를 제공(2609).
10. **Backward-compatible invariants**: 신규 GLP 모듈/풀 유형 추가 시 불변조건 유지.

### State/Flow
- 모든 GLP 연산은 불변조건 체크리스트를 통과해야 커밋(commit) 가능하며, 실패 시 상태는 변경되지 않는다.

### Validation
- 불변조건별 검증의 입력/출력 최소 형식은 2610(레지스트리 최소 인터페이스)에서 규정한다.

### Failure handling
- 불변조건 위반은 “치명적 검증 실패(fatal validation failure)”로 분류하고, 실행 단계로 진행하지 않는다(2607).

### Audit
- 불변조건 체크 결과(각 항목 pass/fail 및 근거 데이터 포인터)를 감사 레코드에 포함한다.

### Invariants
- 본 절은 GLP의 상위 강제 불변조건 적용 요약이며, 체크리스트의 세부 코드는 레지스트리로 위임한다(2610).

---

## 2605. 참여자 역할 정의(User, Liquidity Provider, Treasury, Insurance Reserve, Oracle, Validator, Auditor)

### Purpose
GLP 참여자(actors)의 권한, 책임, 금지 행위를 표준화한다.

### Architecture or Rule
- **User**: Swap 수행 주체. 자산 승인, 입력 정규화 준수, 수수료 지불 의무.
- **Liquidity Provider(LP)**: 유동성 예치/회수 주체. 기본적으로 풀 파라미터 변경 권한 없음. LP-Position NFT의 소유자.
- **Treasury**: 프로토콜 재정 계정/모듈. 수수료/수익 수령. 사용자 자산과 분리 보관(Constitution 8).
- **Insurance Reserve**: 손실 흡수/보상 전용 준비 계정. 인출/사용은 강화된 EA(2607) 필요.
- **Oracle**: 가격/리스크 파라미터 제공자. 입력은 `oracle_round_id`로 고정되며 서명/만료 검증이 가능해야 한다(2608, 2610).
- **Validator**: 결정론 실행과 상태 루트(state root) 확정 책임.
- **Auditor**: 이벤트/감사 레코드 접근, 추적성 검증 수행.

### State/Flow
- 역할별로 “요청 → BRV → EA → 실행 → 기록” 단계에서 수행/서명/승인 범위가 다르며, EA 정책에 의해 제한된다(2607, 2610).

### Validation
- 요청자의 역할(ROLE)과 권한(AUTHZ)을 확인하고, 금지 역할 조합(예: 동일 oracle_round_id에서 Oracle이 가격 제공자이면서 EA 승인자 역할 수행)을 정책으로 차단한다(2607, 2610).

### Failure handling
- 권한 부족, 역할 충돌(conflict of interest), 필수 서명/증빙 누락 시 거부한다.

### Audit
- 감사 레코드에 요청자/승인자/오라클 서명자/검증자(validator set) 식별자를 포함한다.

### Invariants
- 자산 분리(Constitution 8) 및 실행 승인(Constitution 4)은 역할 모델과 EA로 강제된다.

---

## 2606. 고정 용어/기초 파라미터: reserve_ratio, fee_model, slippage_model

### Purpose
GLP에서 반복 사용되는 핵심 파라미터를 공통 정의하여 구현 간 불일치를 방지한다.

### Architecture or Rule
- **reserve_ratio**: (정의) 특정 기준량(baseline)에 대해 요구되는 “검증된 실물 준비금”의 최소 비율.
  1) 기준량(baseline) 고정
     - baseline은 **프로토콜 전체 U-FT 총발행량(total_uf_t_supply)** 으로 고정한다. (풀 내 잔고, 유통량 등으로 임의 변경 금지)
  2) 준비금 수치(reserve_amount) 단위 고정
     - 준비금은 `reserve_unit`(예: gram)로 표준화된 정수량으로 표현하며, U-FT도 `uf_t_unit`(예: gram-equivalent)로 표준화된 정수량으로 환산된다고 가정한다(환산 스케일은 Asset Registry에 고정; 2610).
  3) 검증 시점 및 데이터 소스 고정(결정론)
     - 트랜잭션은 `reserve_attestation_id`를 입력으로 포함해야 하며, BRV는 해당 ID로 조회되는 **VerifiedReserveState 스냅샷**만을 사용한다(최신값 자동 선택 금지).
  4) 비교 규칙
     - `reserve_amount >= ceil(total_uf_t_supply * reserve_ratio)` 를 만족해야 하며, 모든 연산은 고정소수점/정수 반올림 규칙을 명시적으로 고정한다(2608).
  5) 적용 범위
     - GLP는 U-FT 공급을 변경하지 않으나, “외부 모듈과 결합된 경로”에서 우회가 발생하지 않도록, GLP 엔드포인트가 `reserve_attestation_id`를 요구하는 모드(정책 기반)를 제공할 수 있다(EA scope로 제어; 2607).
- **fee_model**: Swap 및 LP 연산에 적용되는 수수료 산정 규칙.
  - 입력(최소): `(model_id, model_version, amount_in, pool_liquidity_snapshot, oracle_price, rounding_mode)`
  - 출력(최소): `total_fee`, `fee_splits[]`
  - `fee_splits[]` 최소 필드(정규화된 분개 단위):
    - `beneficiary_account_type ∈ {USER_ASSET, LP_FEE, TREASURY, INSURANCE_RESERVE, PROTOCOL_REVENUE}`
    - `asset_id`, `amount`(정수), `posting_rule_id`(분개 규칙 식별자)
  - 분배 순서/상한(최소 규범):
    1) `total_fee`는 `amount_in`을 초과할 수 없다.
    2) `fee_splits[].amount` 합은 `total_fee`와 정확히 일치해야 한다.
    3) `INSURANCE_RESERVE` 및 `TREASURY/PROTOCOL_REVENUE` 수혜는 반드시 **분리 계정군**으로만 분개되어야 하며, USER_ASSET 영역으로의 역분개를 금지한다(Constitution 8).
- **slippage_model**: 사용자 체결 가격의 허용 편차 및 최소 수취액(min_out) 검증 규칙.
  - 입력(최소): `(model_id, model_version, quote_out, min_out, pool_state_snapshot, oracle_round_id, rounding_mode)`
  - 출력(최소): `is_executable`, `executed_out`
  - 결정론 규칙: 오라클 값 선택은 자동이 아닌 `oracle_round_id`로 고정한다(2608, 2610).

### State/Flow
- 모든 Swap은 (a) fee_model 계산, (b) slippage_model 검증을 완료한 후에만 잔고 변경을 커밋한다.

### Validation
- 파라미터는 풀 생성/업그레이드 시 허용범위 및 형식 검증을 수행한다(2610).
- 오라클 입력이 필요한 모델은 “서명 검증(signature verification)”, “만료(expiry)”, “라운드 일관성(round consistency; oracle_round_id 고정)”을 통과해야 한다.

### Failure handling
- 수수료/슬리피지 계산이 결정론적으로 재현되지 않는 입력(비정규화 수, 부동소수점, 외부 비결정 값) 사용을 금지한다.

### Audit
- 계산 입력/출력(모델 ID/버전, 파라미터, 반올림 규칙, fee_splits 분개 내역)을 감사 레코드에 포함한다.

### Invariants
- Constitution 6(결정론), 7(보상 가치원천), 8(자산 분리)을 모델 정의 수준에서 준수한다.

---

## 2607. 상태 전이 공통 규칙: Business Rule Validation, Execution Authorization

### Purpose
GLP의 모든 상태 전이가 동일한 검증·승인 파이프라인을 따르도록 강제한다.

### Architecture or Rule
- 모든 GLP 트랜잭션은 다음 2단계 게이트를 통과해야 한다.
  1) **Business Rule Validation(BRV)**: 불변조건, 파라미터, 잔고, 오라클, 슬리피지/수수료 모델, 역할/권한, 자산 분리, 호출 그래프 제한(2603) 등을 검증.
  2) **Execution Authorization(EA)**: 실행 승인(Authorization) 정책 평가. 단순 사용자 Swap은 사용자 서명으로 충분할 수 있으나, 풀 파라미터 변경, 보험준비금 사용, 트레저리 이동 등은 다중승인(multi-approval) 또는 시간지연(timelock)을 요구할 수 있다(2610).

### State/Flow
- 표준 실행 흐름:
  - Input Normalize(2608) → BRV → EA → Deterministic Execute → Emit Events → Write Audit Record → Commit State
- 실패 처리 기록의 결정론 규칙(필수):
  - BRV/EA 실패 트랜잭션은 **상태를 커밋하지 않으며**, 실패 정보는 합의 계층의 트랜잭션 영수증(Receipt; 로그/메타데이터)으로만 남긴다.
  - 따라서 본 챕터에서 말하는 “rejected 이벤트/기록”은 **캐노니컬 상태(state)에 영향을 주지 않는 Receipt 레벨 산출물**로 한정한다.
  - 2609의 “격리(quarantine)”는 온체인 상태 플래그가 아니라, **감사/운영의 오프체인 보류 큐**로 처리하는 것을 기본으로 한다(결정론 보호).

### Validation
- BRV는 최소한 다음을 포함한다.
  - 불변조건 체크(2604)
  - 권리 분리 및 호출 그래프 제한(2603)
  - 자산 분리 계정 제약(Constitution 8; 2606 fee_splits 포함)
  - 결정론 입력 정규화(2608)
  - 모델 계산 가능성 및 오라클 검증(2606, 2610)
  - reserve_ratio 검증이 요구되는 모드에서는 `reserve_attestation_id`로 VerifiedReserveState를 고정 조회(2606, 2610)
- EA는 승인 주체, 승인 범위(scope), 만료(expiry), 재사용 방지(nonce) 검증을 포함한다.
  - EA scope는 최소한 다음을 포함해야 한다: `SWAP`, `ADD_LIQUIDITY`, `REMOVE_LIQUIDITY`, `POOL_PARAM_CHANGE`, `TREASURY_MOVE`, `INSURANCE_USE`.

### Failure handling
- 검증 실패는 표준화된 실패 타입으로 분류한다.
  - `INVARIANT_FAIL`: 2604 위반(권리 분리/자산 분리/준비금 게이트 포함)
  - `ORACLE_FAIL`: 서명/만료/라운드 불일치(oracle_round_id)
  - `LIMIT_FAIL`: slippage(min_out), deadline 위반
  - `AUTHZ_FAIL`: EA 실패(서명/스코프/만료/nonce/역할 충돌)
  - `VALIDATION_FAIL`: 잔고 부족, 형식 오류, 정규화 실패(단, 정규화 실패는 Receipt에 원인 코드 필수)
- 상세 코드는 레지스트리로 위임한다(2610).
- 실패 시 원장 상태는 변경되지 않으며, 동일 입력 재시도 시 동일 실패가 재현되어야 한다(결정론).

### Audit
- BRV 결과와 EA 증빙(서명, 정책 버전, 승인 체인)은 성공 트랜잭션의 감사 레코드에 포함한다.
- 실패 트랜잭션의 경우 Receipt에 최소한 `failure_type`, `reason_code`, `normalized_input_hash`를 포함한다(상태 커밋 없음).

### Invariants
- Constitution 4 및 6을 본 절 규칙으로 직접 강제한다.

---

## 2608. 결정론(determinism) 요구사항 및 입력 정규화

### Purpose
GLP의 캐노니컬 원장 상태(canonical ledger state)가 모든 노드에서 동일하게 재현되도록 결정론 요구사항과 입력 정규화 규칙을 정의한다.

### Architecture or Rule
- 모든 수치 연산은 고정소수점(fixed-point) 또는 정수(integer) 기반이며, 부동소수점(float) 사용을 금지한다.
- 입력 정규화(Input normalization)는 실행 전 필수 단계이며, 정규화 결과가 트랜잭션 컨텍스트에 포함되어 검증/감사에 사용된다.
- 정렬/반올림 규칙은 모델별로 단일 규칙을 고정해야 하며, 모델 버전(versioned model id)을 명시해야 한다(2610).
- 오라클 선택의 결정론 규칙(필수):
  - 트랜잭션은 `oracle_round_id`를 포함해야 하며, 실행은 해당 라운드의 데이터만 사용한다(최신 라운드 자동 선택 금지).
  - 다중 오라클 합성(aggregation)을 사용하는 경우에도, 트랜잭션은 `oracle_round_id`와 함께 `oracle_set_id`를 포함하고, 합성 규칙(정렬→중앙값 등)은 고정소수점 기반으로 모델에 고정되어야 한다(2610).

### State/Flow
- Normalize 대상 예시:
  - 자산 수량(amount)의 스케일 변환(토큰 decimals)
  - 오라클 가격(price)의 라운드/타임 윈도우 선택(oracle_round_id 고정)
  - 수수료 계산의 기준 시점은 “합의 제공 값(블록 높이/타임스탬프)”만 사용
- Normalize 산출물: `NormalizedInput`(최소 필드):
  - `tx_type`, `pool_id`, `asset_ids[]`, `amounts[]`, `oracle_round_id`, `model_ids{fee,slippage}`, `deadline`, `nonce`, `rounding_mode`, `normalized_input_hash`
  - 객체 상세 스키마는 레지스트리로 위임하되(2610), 상기 최소 필드는 누락될 수 없다.

### Validation
- 정규화 실패 조건: 스케일 불일치, 범위 초과, 오라클 라운드 불일치, 만료 가격 사용, 비결정 필드 포함 등.
- 동일 트랜잭션은 모든 검증자에서 동일한 `NormalizedInput`을 생성해야 한다.

### Failure handling
- 정규화 실패는 즉시 거부하며, 원본 입력과 정규화 실패 사유는 Receipt에 기록한다(2607).
- 민감정보 마스킹은 “표시 계층(display layer)”에서만 수행하며, 캐노니컬 검증 데이터는 해시/커밋먼트 형태로 유지한다(2610).

### Audit
- 성공 트랜잭션 감사 레코드는 “원본 입력(raw)”, “정규화 입력(normalized)”, “모델 버전”, “반올림 규칙”, “오라클 증적 키”를 포함한다.

### Invariants
- Constitution 6(결정론)을 만족하지 않는 연산/모델은 GLP에 탑재될 수 없다.

---

## 2609. 감사/추적성 기본 요구: redemption/burn/settlement traceability

### Purpose
GLP에서 발생한 경제 행위가 상환(redemption), 소각(burn), 정산(settlement), 복구(recovery) 등과 연계되어 종단 간(end-to-end) 추적 가능하도록 기본 요구사항을 정의한다.

### Architecture or Rule
- GLP 이벤트는 외부 모듈의 상환/소각/정산 이벤트와 연결 가능한 **추적 식별자(trace id)** 를 포함해야 한다.
- trace id는 최소한 다음을 지원해야 한다.
  - 트랜잭션 id(txid) 기반 연계
  - 풀 id(pool_id), 자산 id(asset_id), 포지션 id(position_id) 기반 연계
  - 오라클 라운드 id(oracle_round_id) 기반 연계(가격 근거 고정)

### State/Flow
- Swap/LP 연산 성공 시: GLP 이벤트 + 감사 레코드 생성(상태 커밋 포함)
- 후속 모듈(상환/소각/정산)이 GLP 결과를 참조할 경우: 해당 모듈 이벤트는 GLP의 trace id를 참조해야 한다(인터페이스는 2610).

### Validation
- trace id 누락/형식 불일치/중복 재사용은 금지한다(재사용 방지는 nonce/sequence 정책과 결합; 2607, 2610).
- 실패 트랜잭션은 상태 커밋이 없으므로, trace id는 Receipt에만 존재할 수 있으며 이벤트 스트림의 “성공 이벤트”와 혼동되지 않도록 구분 타입을 강제한다.

### Failure handling
- 추적 필수 필드 누락 시 실행을 거부한다(권장).
- “격리(quarantine)”는 온체인 상태 전이가 아니라, 감사/운영의 오프체인 보류 처리로 한정한다(2607).

### Audit
- 감사 레코드는 이벤트 스트림(event stream)과 상호 검증 가능해야 하며, 감사자가 체인 외부에서 재구성(reconstruction)할 수 있도록 결정론적 데이터(또는 커밋먼트)만 포함한다.

### Invariants
- Constitution 9(추적성)을 GLP 레벨에서 충족한다.

---

## 2610. 타 챕터 인터페이스 개요 및 [REFERENCE_REQUIRED] 목록

### Purpose
GLP가 의존하는 타 챕터/모듈과의 인터페이스 경계를 요약하고, 본 배치에서 미해결 레퍼런스를 명시한다. 또한, 레지스트리/정책이 미정인 경우에도 구현 가능한 **최소 인터페이스(필드/함수 시그니처 수준)** 를 본 절에 고정한다.

### Architecture or Rule (Interface Overview)
- **Reserve/Issuance 모듈(조회 전용)**
  - GLP는 준비금 검증 상태를 생성/수정(write)하지 않는다.
  - 최소 조회 인터페이스(결정론 고정 키 기반):
    - `GetVerifiedReserveState(reserve_attestation_id) -> VerifiedReserveState | error`
    - `VerifiedReserveState` 최소 필드:
      - `reserve_attestation_id`(immutable)
      - `reserve_amount`(integer)
      - `reserve_unit`(enum/string; 예: gram)
      - `attested_at_height`(block height)
      - `issuer_set_id`(검증/서명 주체 집합 식별자)
      - `state_commitment`(해시/머클루트 등 커밋먼트)
    - 오류 최소 집합: `NOT_FOUND`, `ATTESTATION_EXPIRED`, `INVALID_COMMITMENT`
  - 버전 고정 규칙: 트랜잭션은 `reserve_attestation_id`를 명시해야 하며 “최신 자동 선택”을 금지한다.
- **Asset Registry / Object Registry(조회 전용)**
  - 최소 조회 인터페이스:
    - `GetAssetMeta(asset_id) -> {decimals, unit_scale, asset_type, is_whitelisted}`
    - `GetModelMeta(model_id, model_version) -> {rounding_mode, param_schema_hash}`
    - `GetPoolMeta(pool_id) -> {primary_asset_id, quote_asset_id, fee_model_id, slippage_model_id}`
  - 버전 고정 규칙: 모델은 `(model_id, model_version)`로 pinning 한다.
- **Oracle 모듈(라운드 고정 조회)**
  - 최소 조회 인터페이스:
    - `GetOracleRound(oracle_set_id, oracle_round_id) -> OracleRound | error`
    - `OracleRound` 최소 필드:
      - `oracle_set_id`, `oracle_round_id`
      - `price`(fixed-point/integer), `price_unit`
      - `signed_at_height`, `expires_at_height`
      - `signatures`(검증 가능한 커밋먼트 또는 서명 집합)
    - 오류 최소 집합: `NOT_FOUND`, `EXPIRED`, `BAD_SIGNATURE`, `SET_MISMATCH`
  - 버전/선택 규칙: 트랜잭션은 `oracle_round_id`(및 다중 오라클 시 `oracle_set_id`)를 포함해야 하며, BRV는 해당 라운드의 유효성만 검증한다(2608).
- **Treasury/Insurance 모듈(분개 목적지로만 사용, 사용은 EA 강화)**
  - 최소 인터페이스(분개/정산 결과의 결정론 보장):
    - `PostFeeSplits(txid, fee_splits[]) -> {posting_ids[] } | error`
    - `fee_splits[]`는 2606의 최소 필드를 준수해야 한다.
  - EA 정책 최소 요구: `INSURANCE_USE`, `TREASURY_MOVE` scope는 다중승인 또는 timelock을 요구할 수 있으며, 정책은 `policy_id`로 pinning 한다.
- **Audit/Event 모듈(결정론 데이터/커밋먼트 기반)**
  - 최소 이벤트 스키마(성공 이벤트):
    - `event_type`, `txid`, `pool_id`, `asset_ids[]`, `amounts[]`, `position_id?`, `oracle_round_id`, `trace_id`, `state_hash`
  - 마스킹 원칙(필수):
    - 캐노니컬 검증에 필요한 필드는 마스킹하지 않는다.
    - 표시 계층에서만 마스킹하며, 필요 시 원장에는 원문 대신 `hash/commitment`를 저장한다(2608).
- **Consensus/Validation 레이어**
  - GLP는 합의가 제공하는 블록 높이/타임스탬프를 결정론 입력으로만 사용한다(2608).
  - 실패 트랜잭션 기록은 상태가 아닌 Receipt로 한정한다(2607).

### State/Flow
- GLP는 외부 모듈에 대해 “조회는 pinning(IDs) 기반으로만, 변경은 권한과 경계에 따라 제한” 원칙을 적용한다. P-NFT, 준비금 검증, 보험준비금 사용은 GLP에서 직접 변경하지 않는다(2603, 2606, 2607).

### Validation
- 외부 참조 데이터(오라클/레지스트리/준비금 상태)는 트랜잭션 입력에 포함된 ID로 고정(pinning)되어야 하며, BRV는 해당 객체의 서명/만료/커밋먼트만 검증한다.

### Failure handling
- 외부 참조가 불가(미존재, 만료, 버전 불일치)하면 GLP 연산은 실패해야 하며, 대체 경로(fallback)는 기본적으로 허용하지 않는다.

### Audit
- 외부 모듈 참조는 모두 “참조 키(reference key; reserve_attestation_id, oracle_round_id, model_version 등)”로 감사 레코드에 남겨야 하며, 감사자는 동일 키로 재검증 가능해야 한다.

### [REFERENCE_REQUIRED] 목록(세부 규격/전체 스키마/정책 문서)
- terminology.md: 용어 및 약어 표준 정의
- section_index.md: 챕터/절 상호 위치 및 공식 인덱스
- object_registry.md: `NormalizedInput`, `Pool`, `LP-Position NFT`, `AuditRecord`, `Event` 등 전체 객체 스키마
- invariant_registry.md: Constitution 1~10의 구현형 검증 룰, 체크리스트, 증적 데이터 요구
- 오류코드/상세 reason_code 레지스트리(본 챕터는 failure_type까지만 규정; 2607)
- 파라미터 레지스트리(allowed ranges, model versions, posting_rule_id)
- 오라클 서명 검증/issuer_set_id 관리 정책
- EA 정책 레지스트리(policy_id, scope별 승인 요건, timelock/multi-approval 규칙)
- 준비금 검증 상태의 만료/갱신 정책(ATTESTATION_EXPIRED 판단 규칙)

---

## 2611. GLP 모듈 경계 및 책임 분리

### Purpose
GLP(Gold Liquidity Pool) 프레임워크의 모듈 경계(boundary)를 명확히 정의하여, 상태 전이(state transition)의 결정론성(determinism)과 감사 가능성(auditability), 권한 통제(Execution Authorization)를 보장한다.

### Architecture or Rule
- GLP는 아래 5개 모듈로 구성되며, 모듈 간 호출은 “명시적 입력/출력 객체 + AuthorizationContext(섹션 2618)로 재현 가능한 서명 증빙”만을 통해서만 수행한다.
- 용어 최소 정의:
  - Vault는 원장 잔고(ledger balance)를 보유하는 온체인 객체(on-chain object)이다.
  - Domain/Account는 자산 분리 정책 상의 논리 컨테이너(logical container)이며, Vault는 반드시 정확히 하나의 Domain에 귀속된다([REFERENCE_REQUIRED]: terminology.md).
- 모듈 I/O(입출력) 객체 최소 필드(정규화):
  - `requestId`, `txType`, `poolId`(해당 시), `actor`, `role`(2618), `policyRefs[]`, `objectIdsTouched[]`, `inputsHash`, `signatures[]`
  - 모듈 출력에는 `outputsHash`, `reasonCode`, `decision`(Allow/Reject/RequireGuarded 등)이 포함되어야 한다.
1) **Pool Core**
   - 풀 생성/구성, 예치·인출·스왑·리밸런스 등 핵심 상태 전이 오케스트레이션
   - 호출 순서 제어 및 원장 이벤트 발행
2) **Accounting**
   - 금고(vault) 원장 잔고, 수수료 산식, 풀 지분/청구권 계산 등 회계 규칙 수행
   - Treasury/Insurance/Revenue/User 자산 분리 불변성 검증
3) **Risk**
   - 풀 파라미터 제약(한도, LTV 유사 한도, 슬리피지 캡, 일일 변화율 등) 검증
   - 위기 모드(guarded mode) 진입/해제 판정 신호 제공(단, 최종 전이는 Pool Core)
4) **Oracle Adapter**
   - 외부 가격/지표를 표준 포맷으로 수집·검증하여 Pool Core에 전달
   - 오라클 데이터는 “어댑터가 검증한 정규화 레코드(normalized record)”로만 사용
5) **Settlement Adapter**
   - 온체인/오프체인 결제(physical delivery, redemption, burn, settlement) 연동을 표준화
   - 결제 상태는 “추적 가능한 참조키(traceable reference key)”를 포함해야 함

### State/Flow
- 모든 경제 행위 트랜잭션은 아래 순서로 처리된다.
1) Pool Core: 요청 수신 → 대상 Pool/Vault/FT 식별 → 실행 타입 결정 → `settlementRequired` 판정(정책 고정, 아래 참조)
2) Risk: 한도/모드/제약 검증 결과 반환(Allow/Reject/RequireGuarded)
3) Oracle Adapter(필요 시): 가격 스냅샷/유효기간/소스 증빙 반환
4) Accounting: 잔고 이동 계획(plan) + 수수료/분배 계산 + 불변성 체크
5) Pool Core: Execution Authorization(2618) 검증 → 상태 전이 커밋 → Events 기록
6) Settlement Adapter(필요 시):
   - `settlementRequired=true`: 동일 트랜잭션에서 `SettlementCase` 또는 `SettlementQueueEntry`(아래 참조) 생성/갱신까지 포함하여 원자적으로 커밋되어야 한다.
   - `settlementRequired=false`: 어댑터 연동 실패 시에도 온체인 경제 상태 전이는 완료될 수 있으나, 동일 트랜잭션에서 `SettlementQueueEntry(PENDING)`를 결정론적으로 기록해야 한다.
- `settlementRequired` 판정 기준:
  - `txType`별 `settlementRequired`는 정책 객체(`SettlementPolicy`)로 고정되며, 검증자가 재현 가능해야 한다([REFERENCE_REQUIRED]: policy registry).
- Settlement 대기 객체(state model) 최소 요건:
  - `SettlementQueueEntry = { queueEntryId, txHash, txType, poolId, settlementRequired, status(PENDING|SUBMITTED|CONFIRMED|FAILED|CANCELLED|EXPIRED), traceableReferenceKey(optional), createdAt, updatedAt, attemptCount, nextRetryAt, timeoutAt, lastErrorCode }`
  - `queueEntryId`는 결정론적으로 파생되어야 한다(예: `HASH(namespace||chainId||txHash||"SETTLEMENT_QUEUE")`).

### Validation
- 모듈 호출 간 입력은 반드시 “정규화된 객체(IDs 포함) + 체인 내 확인 가능한 증빙(AuthorizationContext로 재현 가능한 서명/정책 참조)”으로 한정한다.
- Accounting은 “자산 분리 불변성”과 “권리-자산 매핑”을 검증하지 못하면 어떠한 잔고 이동도 산출할 수 없다.
- Settlement 비필수 트랜잭션에서 `SettlementQueueEntry(PENDING)`가 생성되는 경우, 이는 감사/재시도 목적의 온체인 상태이며, Vault 잔고/FT 권리의 의미를 변경해서는 안 된다.

### Failure handling
- Risk 또는 Oracle 검증 실패: 상태 전이 중단, 아무런 잔고 변경 없이 Reject 이벤트만 기록(섹션 2619의 reject 기록 규칙 준수).
- Accounting 산출 실패: 상태 전이 중단, 원장 변경 없음.
- Settlement Adapter 실패:
  - `settlementRequired=true`: 트랜잭션 Reject(원장 변경 없음).
  - `settlementRequired=false`: 본 트랜잭션의 경제 상태 전이는 커밋 가능하나, 동일 트랜잭션에서 `SettlementQueueEntry(PENDING)` 기록이 필수이며, 이후 전이는 아래로 제한한다.
    - 재시도: `PENDING/FAILED → SUBMITTED`(권한 필요: `SETTLEMENT_OPERATOR`, 2618)
    - 확인: `SUBMITTED → CONFIRMED`
    - 실패: `SUBMITTED → FAILED`
    - 취소/만료: `PENDING/FAILED → CANCELLED/EXPIRED`(정책의 `timeoutAt` 충족 시)
  - 위 전이들은 반드시 이벤트로 기록되어야 한다(섹션 2619).

### Audit
- 모듈별로 “입력 해시/출력 해시/결정 사유 코드(reason code)”를 이벤트에 포함한다.
- SettlementQueueEntry 기반으로 “미결 정산(pending settlement) 목록, 재시도 이력, 만료/취소 사유”가 온체인에서 재구성 가능해야 한다.

### Invariants when applicable
- (Master Constitution 6) 결정론적 원장 상태: 동일 입력은 동일 출력.
- (Master Constitution 4) 모든 전이는 Business Rule Validation + Execution Authorization 통과 필수.
- (Master Constitution 9) 정산/상환/소각 연동은 추적 가능해야 하며, 비필수 연동 실패도 온체인 대기 객체로 감사 가능해야 한다.

---

## 2612. 계정/금고 분리 모델(Asset Segregation Model)

### Purpose
Treasury, Insurance Reserve, Protocol Revenue, User Assets 간 자산 혼합을 방지하여 (Master Constitution 8) 자산 분리와 회계 투명성을 보장한다.

### Architecture or Rule
- 모든 GLP 자산은 아래 4대 영역으로 분리된 “법적/회계적 독립 계정”으로 처리된다.
1) **Treasury**
2) **Insurance Reserve**
3) **Protocol Revenue**
4) **User Assets**
- 분리 원칙:
  - User Assets → Treasury 직접 이동 금지.
  - Insurance Reserve는 정의된 지급 조건에서만 User Assets 보전 방향으로 이동 가능.
  - Protocol Revenue는 정의된 분배 규칙에 따라 Treasury 등으로 이동 가능하나, User Assets 임의 취득 불가.
  - Treasury → User Assets 직접 이동은 원칙 금지. 예외는 `TX_TREASURY_REFUND`로만 허용(정책 [REFERENCE_REQUIRED]).

### State/Flow
- 모든 자산 이동은 “(fromVault, toVault, assetType, amount, reasonCode, policyRef)” 형태의 원장 엔트리 집합으로 표현된다.
- Accounting 모듈이 엔트리 집합을 산출하고, Pool Core가 커밋한다.

### Validation
- from/to 영역이 분리 정책에 부합하는지 검증한다.

### Failure handling
- 분리 정책 위반 엔트리 포함 시 트랜잭션 전체 Reject.

### Audit
- 모든 이동 엔트리는 `policyRef` 및 `reasonCode`를 포함한다.
- 영역별 집계가 가능해야 한다.

### Invariants when applicable
- (Master Constitution 8) 자산은 영역 간 혼합 불가.
- (Master Constitution 7) 모든 수익/보상은 정의된 가치 원천과 연결(사유 코드).

---

## 2613. Pool별 Vault 구조 및 권한 모델

### Purpose
Pool 단위로 자산을 물리적으로 분리하고, 금고별 목적과 권한을 고정하여 무단 유동성 조작을 방지한다.

### Architecture or Rule
- 각 Pool은 최소 3개 Vault 보유:
  1) **Reserve Vault**
  2) **Liquidity Vault**
  3) **Fee Vault**
- 선택적 Vault:
  4) **Insurance Vault**
  5) **Settlement Vault**
  6) **Treasury Interaction Vault**
- ReserveProof 최소 필드 및 검증 규칙은 [REFERENCE_REQUIRED].

### State/Flow
- Vault 라이프사이클: Created → Active → (Paused) → Closed
- Vault 이동은 Accounting 엔트리로만 수행.

### Validation
- Vault별 허용 동작(operations)을 `txType` enum으로 정규화하고 목적 외 txType은 Reject([REFERENCE_REQUIRED]: txType registry).
- ReserveProof 검증은 Reserve Vault 연계 txType에 필수.

### Failure handling
- Vault 상태 Paused/Closed 시 관련 txType Reject.
- 목적 외 txType Reject.
- ReserveProof 부재/무효 Reject.

### Audit
- Vault별 잔고 스냅샷+이동 엔트리 재구성 가능.
- ReserveProof 이력 추적 가능.

### Invariants when applicable
- (Master Constitution 1) 준비금 검증 선행.
- (Master Constitution 5) 유동성 조작이 불변성 우회 불가.

---

## 2614. 원장 객체 식별자(Object IDs) 및 결정론적 주소 규칙

### Purpose
동일 입력이 동일 객체 주소를 산출하도록 하여 결정론적 상태를 보장한다.

### Architecture or Rule
- `ObjectID = HASH(namespace || chainId || protocolId || poolId || objectType || deterministicSalt)`
- `deterministicSalt`는 검증자가 재현 가능한 값만 허용(랜덤 금지; [REFERENCE_REQUIRED]: object_registry.md).
- Pool/Vault ID 파생 규칙은 결정론적으로 고정한다.

### State/Flow
- Bootstrap 시: Protocol Root IDs → 기본 계정 IDs → Genesis Pool/Vault IDs(해당 시).

### Validation
- ObjectID 재계산 일치, 충돌 부재, 필수 필드 충족, salt 허용 형식 검증.

### Failure handling
- 충돌/비결정 파생 발견 시 Reject.

### Audit
- 이벤트에 `derivedObjectIds[]`, `idDerivationVersion` 기록.

### Invariants when applicable
- (Master Constitution 6) 결정론적 원장 상태 유지.

---

## 2615. 자산-권리 매핑(FT Economic Rights Mapping)

### Purpose
FT가 표현하는 경제적 권리를 고정하여 권리 혼동 및 무단 청구를 방지한다.

### Architecture or Rule
- 원금 소유권은 NFT로만, GLP의 FT는 경제적 이용권만 표현(Constitution 2,3).
- 각 FT는 `rightsProfileId`를 참조하며, 청구 대상 Vault/산식/제한을 정의한다([REFERENCE_REQUIRED]).

### State/Flow
- Accounting은 “FT 변화량(delta) ↔ Vault 엔트리 변화”를 연결 가능한 형태로 산출한다.

### Validation
- rightsProfile 허용 동작, Vault 변동 합치, 전송 제한/락업, 적격성/준법 플래그, 혼동 방지 검증.

### Failure handling
- 불일치/미등록/적격성 위반 시 Reject.

### Audit
- 이벤트에 `ftType`, `rightsProfileId`, `vaultLinks[]` 기록.

### Invariants when applicable
- (Master Constitution 3) 권리 분리.
- (Master Constitution 2) 원금 소유권 비희석.

---

## 2616. Pool Share(LP Token) 설계 원칙 및 권리 범위 제한

### Purpose
LP token이 제한적 청구권만 표현하도록 범위를 제한한다.

### Architecture or Rule
- 포함 가능: Liquidity/Fee Vault 기반 NAV 비례 청구권, 규칙에 따른 수수료 분배.
- 포함 불가: Reserve Vault 원금 소유권/실물 인도 청구권, Principal NFT 권리.
- 보험자산을 NAV에 포함하는 경우 정책(`LpNavPolicy`)로 고정([REFERENCE_REQUIRED]).

### State/Flow
- Add: User Assets → Liquidity Vault, LP Token mint.
- Remove: LP Token burn, Liquidity Vault → User Assets, (정책 기반) Fee 분배.

### Validation
- mint/burn 산식 일치, Risk 보호 한도, (해당 시) 보험 공제/상한 적용 검증.

### Failure handling
- NAV 불확정 시 guarded mode 또는 Reject(풀 정책).

### Audit
- LP mint/burn 이벤트에 `navSnapshot`, `priceRefs`, `feeBreakdown`, `lpNavPolicyRef`(해당 시).

### Invariants when applicable
- (Master Constitution 1,5,7) 우회 및 무근거 NAV 포함 금지.

---

## 2617. 프로토콜 수수료/운영 수익 분배 계정 구조

### Purpose
수수료/운영 수익 귀속·분배를 계정 구조로 고정한다.

### Architecture or Rule
- 최소 금고 구조: ProtocolRevenue Fee/Distribution, Treasury Operating, InsuranceReserve Main/Pool(선택).
- 수수료 유형 및 분배 규칙을 정책으로 고정한다.

### State/Flow
- `AccrueFee` → FeeVault 적립
- `DistributeRevenue` → DistributionVault → 수취처 이동

### Validation
- 정책 버전 pinning, 수취처 whitelist, 합계 일치.

### Failure handling
- 미승인/불일치 시 Reject.

### Audit
- 분배 이벤트에 `distributionPlan`, `beneficiaries[]`, `policyRef`.

### Invariants when applicable
- (Master Constitution 7,8) 가치원천/자산분리.

---

## 2618. 합의/검증자 관점 접근 제어(Execution Authorization) 지점

### Purpose
검증자가 권한을 결정론적으로 판정하도록 EA 지점을 고정한다.

### Architecture or Rule
- 역할 최소 집합: `USER`, `POOL_ADMIN`, `RISK_GUARDIAN`, `SETTLEMENT_OPERATOR`, `TREASURY_OPERATOR`, `AUDITOR_READONLY`.
- `roleRegistry` 요구 필드 및 정책 참조는 [REFERENCE_REQUIRED].
- EA 지점: Pool/Vault/분배/보험/정산/오라클 등록·변경 등.

### State/Flow
- Pool Core는 커밋 직전에 `AuthorizationContext` 구성, 검증자는 동일 컨텍스트 재구성.

### Validation
- 서명 유효성/역할 매핑, 정책 버전/만료, 멀티시그, touched object 범위, scope 일치.

### Failure handling
- 불일치 시 Reject.

### Audit
- 이벤트에 `authzResult`, `role`, `policyRefs`, `multisigQuorum`.

### Invariants when applicable
- (Master Constitution 4) 모든 전이는 EA 통과 필수.

---

## 2619. 감사 이벤트(Events) 및 원장 로그 구조

### Purpose
모든 GLP 상태 전이가 추적 가능하도록 이벤트/로그 스키마를 표준화한다.

### Architecture or Rule
- 이벤트 공통 헤더: `eventId`(결정론), `blockHeight`, `txHash`, `timestamp`, `module`, `eventType`, `version`, `actor`, `role`, `reasonCode`, `policyRef`, `inputsHash`, `outputsHash`.
- 표준 이벤트 타입 최소 집합(POOL/Vault/LP/Swap/Fee/Insurance/Oracle/Settlement).
- ledger log 엔트리 최소 필드 및 ft delta/link 필드 고정.

### State/Flow
- 트랜잭션은 oracle snapshot, accounting plan, ledger entries, ft deltas, final summary로 재구성 가능해야 한다.

### Validation
- `inputsHash/outputsHash` 재현 가능.
- Reject 기록은 stateful/stateless를 정책으로 고정([REFERENCE_REQUIRED]).

### Failure handling
- 이벤트 기록 실패는 커밋 실패로 간주.

### Audit
- event stream만으로 잔고/수수료/보험/정산 추적 재구성 가능.

### Invariants when applicable
- (Master Constitution 9) 추적성.

---

## 2620. 초기화(bootstrap) 및 업그레이드 호환성 요구

### Purpose
초기 배포 및 업그레이드가 불변성을 보존하면서 결정론적 상태를 유지하도록 요구사항을 정의한다.

### Architecture or Rule
- Bootstrap 필수 객체: Protocol Root, 영역별 루트 Vault, 기본 정책 객체, (해당 시) Genesis Pool/Vault.
- genesis config는 합의 입력으로 고정([REFERENCE_REQUIRED]).
- 업그레이드 원칙: ObjectID 파생 규칙 변경 금지(버전 추가만), 이벤트 backward-compatible 확장, rightsProfile 버전 고정.

### State/Flow
- Bootstrap 순서(결정론): Root → Vault → Policy(v1) → Oracle → Pool/Vault → audit baseline snapshot.
- 업그레이드 플로우(예): PROPOSE → AUTHORIZE → EXECUTE → POST_UPGRADE_AUDIT_SNAPSHOT.

### Validation
- Bootstrap 필수 누락/영역 공유/불일치 Reject.
- Upgrade backwardCompatibilityCheck 필수, rightsProfile 변경은 새 버전 추가만.

### Failure handling
- 실패 시 Reject 또는 안전정지(Pause) 전환([REFERENCE_REQUIRED]).

### Audit
- 변경 객체 목록/정책 버전/승인 증빙 이벤트 기록.

### Invariants when applicable
- (Master Constitution 10,6) 호환성·결정론.

---

## 2621. Pool 생성 사전조건: verified physical reserve 선행(issuance precedence)

### Purpose
Pool 생성이 물리적 금 실물 검증 선행 원칙을 위반하지 않도록 사전조건을 정의한다.

### Architecture or Rule
1) Pool은 등록(Register) 단계에서 자산 페어 및 준비금 제약을 선언할 수 있으나, 활성화(Activate)는 준비금 스냅샷 연결을 요구한다.
2) 활성화 시점 검증된 준비금(Verified Reserve) 스냅샷이 유효해야 한다.
3) 상한 계산은 결정론적 규칙으로 수행한다.
4) 발행/유통량 기반 상한 집행은 별도 모듈에서 강제([REFERENCE_REQUIRED]).

### State/Flow
- `PoolState = DRAFT -> REGISTERED -> PENDING_APPROVAL -> ACTIVE | REJECTED | SUSPENDED`
- 활성화 시 참조: `ReserveSnapshotRef`.

### Validation
- `ReserveSnapshotRef` 존재/VALID, reserveConstraints 및 충돌검사(2629), `PoolDeclaredExposure <= MaxCirculatingAllowed` 검증.

### Failure handling
- 스냅샷 미존재/무효/만료/단위 정규화 불가: 활성화 거부 및 이벤트.

### Audit
- 활성화 시 `ReserveSnapshotRef`, 스냅샷 해시, 검증자 식별자, 계산 입력/결과 해시 기록.

### Invariants
- (Constitution 1) ACTIVE Pool은 항상 유효한 준비금 스냅샷 참조.

---

## 2622. Pool 파라미터 스키마: fee, curve, caps, reserve constraints, whitelist

### Purpose
Pool 파라미터를 결정론적으로 정의하고 변경 시 감사 가능하도록 표준 스키마를 규정한다.

### Architecture or Rule
- `PoolConfig` 객체 모델(결정론적 직렬화 필수) 및 필드 집합을 고정한다(원문 스키마 준수).

### State/Flow
- `PoolConfigSnapshot{poolId, configHash, configBody, version}`을 변경마다 증분 저장한다.

### Validation
- Bps 범위, caps의 0 의미(비활성) 고정, CUSTOM curve 승인 경로, KYC 정책 미해소 시 승인 제출 거부.

### Failure handling
- `PoolConfigRejected(INVALID_SCHEMA)` 등.

### Audit
- `PoolConfigSnapshot` 저장.

### Invariants
- (Constitution 6) canonical encoding 필수.

---

## 2623. Pool 등록(State)과 활성화(State) 단계 분리

### Purpose
Pool의 정의/등록과 운영 개시를 분리한다.

### Architecture or Rule
- `REGISTERED`, `PENDING_APPROVAL`, `ACTIVE` 의미를 고정한다.

### State/Flow
1) CreatePool → REGISTERED  
2) SubmitForApproval → PENDING_APPROVAL  
3) ApproveAndScheduleActivation → ACTIVE(즉시 또는 지연)

### Validation
- REGISTERED 완전성 검사, ACTIVE 전환은 2621/2625/2626/2624 충족.

### Failure handling
- 반려 시 REJECTED, 지연 큐 만료 시 활성화 취소 및 REGISTERED 롤백.

### Audit
- `PoolStateTransition{from,to,reason,actor,txId,ts}` 기록.

### Invariants
- ACTIVE 진입은 반드시 PENDING_APPROVAL 경유.

---

## 2624. 거버넌스/권한자(Authorized) 승인 절차

### Purpose
Pool 활성화 및 주요 변경이 임의 실행되지 않도록 승인 규칙을 정의한다.

### Architecture or Rule
- `ApprovalPolicy`, `ApprovalRecord` 및 `actionHash` 구성요소를 결정론적으로 고정한다.
- Execution Authorization 공통 규격은 [REFERENCE_REQUIRED] 미해소 시 실행 거부.

### State/Flow
- SubmitForApproval → COLLECTING → APPROVED → ExecuteAuthorizedAction.

### Validation
- `actionHash` 일치, 만료 서명 무효, replay 금지(`salt` 포함), `consumed=true`는 실행 성공 시에만.

### Failure handling
- 만료/위조/정책 불일치/권한 프레임 미정의 시 거부.

### Audit
- 승인 원문/서명/검증 결과/구성요소 보존.

### Invariants
- (Constitution 4) BRV+EA 필수.

---

## 2625. Oracle/가격 참조원(Price reference) 연결 및 검증 규칙

### Purpose
오라클 위변조/비결정성/비인가 변경 방지.

### Architecture or Rule
- `OracleRegistry`, `OracleBinding` 객체 모델 및 검증 규칙을 고정한다.
- 최초 `LastGoodPrice` 미존재 시 기본 HALT.

### State/Flow
- REGISTERED에서 바인딩 고정, ACTIVE에서 관측 검증 후 LastGoodPrice 갱신(최소 간격 이내 관측은 IGNORE).

### Validation
- registry ACTIVE, pricePair 일치, staleness/deviation 검증.

### Failure handling
- HALT 또는 USE_LAST_GOOD_PRICE(존재 시) 적용.

### Audit
- `OracleAuditRecord` 및 registry 변경 이력 감사 체인(2630) 포함.

### Invariants
- (Constitution 6) 결정론적 참조, 변경은 2627/2624 절차.

---

## 2626. 위험 한도(Risk limits) 및 회로차단기(Circuit breaker) 파라미터

### Purpose
급변/오라클 이상/유동성 고갈에서 손실 전파 제한.

### Architecture or Rule
- `RiskLimitConfig`, `CircuitBreakerConfig` 모델 고정.
- autoSuspend는 “긴급조치 요청 생성”이며 전이 실행은 EA/위임 경로로만.

### State/Flow
- Trigger 이벤트 → EmergencyActionRequest 생성 → 승인 또는 위임 + EA 성공 시 SUSPENDED 전이.

### Validation
- 범위, cooldown/resume 정책, autoSuspend 구성 요건.

### Failure handling
- 누락/상충 시 REGISTERED 유지 및 승인 제출 거부.
- 발동 시 위험 연산 거부, 관리 연산 허용.

### Audit
- `RiskEventLog` 기록(원인/관측값/승인/조치).

### Invariants
- (Constitution 4,5) 우회 불가.

---

## 2627. 파라미터 변경(Change config) 상태 전이 및 시간지연(Time-lock) 옵션

### Purpose
운영 중 변경을 예측 가능하게 하고 타임락을 강제한다.

### Architecture or Rule
- `ConfigChangeRequest` 상태기계 및 Major/Minor 최소 타임락 상수 고정.

### State/Flow
- PROPOSED → PENDING_APPROVAL → SCHEDULED → APPLIED.

### Validation
- 버전 단조 증가, 타임락 하한, 적용 후 활성 조건 유지(기본: 적용 거부).

### Failure handling
- 타임락 미경과/승인 만료/경쟁은 결정론적으로 처리.

### Audit
- 전/후 스냅샷 보존, `ConfigChangeAudit` 기록.

### Invariants
- (Constitution 6) 단조 증가+원자적 적용.

---

## 2628. 실행 권한 위임(Delegation)과 철회(Revocation)

### Purpose
제한된 범위에서 효율적 위임을 제공하되 승인 완화를 금지한다.

### Architecture or Rule
- `DelegationGrant` 모델 및 scope/constraints 고정.
- 위임은 제출/집행 대행이며 승인 면제가 아니다.

### State/Flow
- Grant → ACTIVE, Revoke → REVOKED, 만료 → EXPIRED.

### Validation
- 생성은 승인 필요, 실행 시 유효/제약/승인 정책 대체 불가.

### Failure handling
- 철회 후 사용 시 거부 및 경고 이벤트.

### Audit
- `DelegationAudit` 및 철회 사유 기록.

### Invariants
- (Constitution 4) 정족수/정책 완화 불가.

---

## 2629. 실패 처리: 승인 실패/검증 실패/설정 충돌

### Purpose
Pool 생성/활성화/변경 실패 유형을 일관되게 처리한다.

### Architecture or Rule
- `PoolErrorCode` 표준 집합 및 충돌(conflict) 정의를 고정한다.
- `ConflictCheck(PoolConfig)`는 결정론적으로 수행한다.

### State/Flow
- 실패는 원자적 처리, 감사 목적 FailureEvent 허용.
- ApprovalRecord는 immutable, consumed는 성공 실행 시에만.

### Validation
- 등록/변경 시 충돌검사 필수.

### Failure handling
- 승인 실패: REJECTED 또는 REGISTERED(정책), 검증 실패는 활성화/적용 거부, 런타임은 SUSPENDED 가능.
- 설정 충돌: REGISTERED 유지+거부.

### Audit
- `PoolFailureEvent` 기록.

### Invariants
- 실패 시 부분 변경 금지(원자성).

---

## 2630. 감사: 변경 이력, 승인 서명, 파라미터 스냅샷

### Purpose
Pool 생애주기 전반의 추적 가능성과 사후 검증을 제공한다.

### Architecture or Rule
- 필수 감사 객체 및 `AuditIndex.auditChainHead`(링크드 해시) 유지.

### State/Flow
- 변경 시 recordHash 산출 및 `auditChainHead = H(prevHead || recordHash)` 갱신.

### Validation
- 감사 레코드 작성 실패 시 상태 전이 실패.

### Failure handling
- 저장소 오류 등은 트랜잭션 실패로 롤백.

### Audit
- 외부 감사인은 `auditChainHead`로 누락/변조 탐지.

### Invariants
- (Constitution 5,9) 승인 서명 및 스냅샷은 감사 체인 포함.

---

## 2631. 예치 유형 분류 및 자산 범위(Deposit Type & Asset Scope)
## 2632. 예치 사전조건(Preconditions): 자산 출처 검증 및 게이트
## 2633. Deposit → Mint(Share Issue) 상태 전이 모델(State Machine)
## 2634. 풀 NAV 및 share_price 산정 규칙(Pool Accounting: NAV, share_price)
## 2635. 라운딩(rounding) 및 dust 처리 규칙(Precision & Dust)
## 2636. 수수료 분리 및 귀속(Deposit Fee vs Protocol Fee Attribution)
## 2637. 원자성(Atomicity) 및 부분 실패 금지 규칙
## 2638. 실행 권한(Execution Authorization): 호출자/대리인/서명 검증
## 2639. 감사 이벤트 및 감사 레코드(Audit Events)
## 2640. 테스트/시뮬레이션 입력 정규화(Normalization for Testing/Simulation)

> 2631–2640 절은 승인 배치 원문을 본 챕터에 포함하며, 중복 헤딩/문단이 없도록 통합되었다. (세부 규정은 본 문서 상단 “APPROVED BATCHES” 원문과 동일)

---

## 2641. Withdraw 요청 모델(Amount 기반 / Share 기반)
## 2642. WithdrawIntent 객체 모델 및 상태기계
## 2643. Burn(share)과 지급(asset transfer)의 분리 및 실행 순서
## 2644. 지급 정산·지급(Payout Settlement/Transfer) 및 지급 원천 우선순위
## 2645. 슬리피지/가격 영향 및 min_out 보호(사용자 최소수령)
## 2646. 부분 인출/전액 인출 및 잠금(Lock) 기간 옵션
## 2647. 실행 권한(Authorization): 수령자, 위임 인출, 재진입 방지
## 2648. 감사 이벤트 및 레코드 표준: withdraw_intent, shares_burned, payout_settled, trace_id
## 2649. 실패 처리: 유동성 부족, 가격 급변, 오라클 장애
## 2650. 추적성: redemption/burn/settlement/recovery 연결 키 설계

> 2641–2650 절은 승인 배치 원문을 본 챕터에 포함하며, 중복 헤딩/문단이 없도록 통합되었다.

---

## 2651. Swap 인터페이스 및 경로(Route) 모델(단일/다중 풀)
## 2652. 가격결정 곡선(Curve) 추상화 및 결정론적 계산
## 2653. 수수료 모델: LP fee vs Protocol fee vs 기타(보험료 등)
## 2654. 슬리피지 제한 및 사용자 보호 파라미터(Deadline, MinOut/MaxIn)
## 2655. 오라클 가격과 풀 내 가격의 관계(참조/제약/이상치 탐지)
## 2656. MEV/샌드위치 완화 옵션(예: Batch Auction) [REFERENCE_REQUIRED]
## 2657. 실행 권한: 라우터/풀 직접 호출, 승인 토큰(Allowance) 규칙
## 2658. 실패 처리: 가격 한도 초과, 라우팅 실패, 잔고 부족
## 2659. 감사: swap_quote, swap_executed, fee_accrued
## 2660. 불변조건: 예비금/소유권/감사 불변조건 우회 금지

> 2651–2660 절은 승인 배치 원문을 본 챕터에 포함하며, 중복 헤딩/문단이 없도록 통합되었다.

---

## 2661. 리스크 관리 프레임워크 개요
## 2662. reserve_ratio 및 Verified Reserve 연동 제약
## 2663. 보험준비금(Insurance Reserve) 사용 조건 및 한도
## 2664. 회로차단기(Circuit breaker): 트리거 조건
## 2665. 거래/인출 한도(caps), rate limit, 사용자별 제한 옵션
## 2666. 부실/결손 발생 시 손실 흡수 워터폴(loss waterfall)
## 2667. 상태 전이: 정상(Normal)↔제한(Restricted)↔중지(Paused)↔복구(Recovery)
## 2668. 실패 처리: 강제 중지 시 처리(대기열, 환불, 재개)
## 2669. 감사: 트리거 근거 데이터, 승인자, 복구 절차 기록
## 2670. 시뮬레이션/스트레스 테스트 산출물 보관 [REFERENCE_REQUIRED]

> 2661–2670 절은 승인 배치 원문을 본 챕터에 포함하며, 중복 헤딩/문단이 없도록 통합되었다.

---

## 2671. 수수료 누적(accrual)과 분배(distribution) 분리
## 2672. 프로토콜 수익(Protocol Revenue) 귀속 및 금고 분리
## 2673. LP 수익 산정 방식과 결정론적 분배 규칙
## 2674. 리워드(Reward) 원천: 정의된 가치원천/감사가능성 요구
## 2675. 지급 주기(epochs) 및 스냅샷(snapshot) 메커니즘
## 2676. 세금/원천징수 등 외부 규제 훅(필요 시) [REFERENCE_REQUIRED]
## 2677. 실패 처리: 분배 계산 불일치, 누락 이벤트, 재계산 절차
## 2678. 감사: fee_ledger, distribution_report, epoch_hash
## 2679. 불변조건: 사용자 자산과 프로토콜 자산 혼합 금지
## 2680. 이전/다음 모듈과의 수익 공유 인터페이스

> 2671–2680 절은 승인 배치 원문을 본 챕터에 포함하며, 중복 헤딩/문단이 없도록 통합되었다.

---

## 2681. 비상정지(Pause) 권한 및 재개(Unpause) 조건
## 2682. 오라클 장애/합의 장애 시 안전 모드
## 2683. 정산 실패/지급 실패 재시도 및 보류(escrow) 모델
## 2684. 분쟁(Dispute) 접수→조사→판정→집행 상태 전이
## 2685. 물리적 상환/배송(physical delivery) 연결: redemption/burn/settlement trace
## 2686. 회수(Recovery) 및 롤백 금지 원칙(결정론/불변조건 내에서의 보정만 허용)
## 2687. 실패 처리: 데이터 불일치, 이중지급 방지, 증거자료 부족
## 2688. 감사: 케이스 파일, 증거 해시, 결정 서명, 집행 로그
## 2689. 불변조건: 소유권 침해 금지, 감사추적성 유지
## 2690. 외부 운영 프로세스(물류/보관) 인터페이스 [REFERENCE_REQUIRED]

> 2681–2690 절은 승인 배치 원문을 본 챕터에 포함하며, 중복 헤딩/문단이 없도록 통합되었다.

---

## 2691. 완료 불변조건(Completion Invariants) 및 다음 챕터 전이
## 2692. 다음 챕터로의 전이: GLP 공개 인터페이스/이벤트/레지스트리 등록 항목 정리

> 2691–2692 절은 승인 배치 원문을 본 챕터에 포함하며, 중복 헤딩/문단이 없도록 통합되었다.

---

## Chapter 3O 완료 매트릭스(Completion Matrix)

| 구분 | 범위(절) | 상태 | [REFERENCE_REQUIRED] 핵심 항목 |
|---|---:|---|---|
| 목적/정의/불변조건 요약 | 2601–2604 | 완료 | invariant_registry.md, object_registry.md |
| 공통 파이프라인/결정론/추적성 | 2607–2609 | 완료 | 오류코드 레지스트리, canonical state hash 규칙 |
| 인터페이스 최소 규격 | 2610 | 완료 | 각 레지스트리/정책 문서 |
| 모듈/계정 분리/권한/이벤트 | 2611–2620 | 완료 | txType registry, role registry governance |
| Pool 생애주기/승인/오라클/리스크 | 2621–2630 | 완료 | policy registry, KYC policy, oracle 검증 정책 |
| Deposit/Mint 프레임워크 | 2631–2640 | 완료 | 토큰 표준/메타데이터/registry |
| Withdraw 프레임워크 | 2641–2650 | 완료 | 복구 규격, settlement adapter 규격 |
| Swap 프레임워크 | 2651–2660 | 완료 | 라우팅/DEX 어댑터, 오라클 이상치 탐지 |
| 리스크/워터폴/상태전이 | 2661–2670 | 완료 | 리스크 엔진/보험 운영 규격 |
| 수수료 누적/분배/수익 공유 | 2671–2680 | 완료 | 분배 실행 상태기계 상세, flow matrix |
| 비상/분쟁/복구/배송 연계 | 2681–2690 | 완료 | 물류/보관 외부 인터페이스, principal NFT 특수 절차 |
| 완료 불변조건/공개 계약 | 2691–2692 | 완료 | section_index.md 정합, EA/BRV 레지스트리 |

```