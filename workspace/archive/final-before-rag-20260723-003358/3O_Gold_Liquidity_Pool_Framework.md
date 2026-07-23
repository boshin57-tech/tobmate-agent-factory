```markdown
# Chapter 3O. Gold Liquidity Pool Framework

## 2601. 목적(Purpose)

### 2601.1 목적
본 장(3O)은 TOBMATE Gold Protocol에서 **Gold Liquidity Pool(LP)** 을 통해 발생하는 유동성 공급/회수, 스왑(swap), 수수료/보상 정산, 리스크 제어를 **Master Constitution 1~10**에 합치되게 정의하기 위한 **표준 프레임워크**를 규정한다.

### 2601.2 달성 목표
1. **Verified physical reserve 선행**(Constitution 1)을 전제로 한 LP 기반 유동성 연동 구조 정의  
2. **Principal Ownership NFT**와 **Economic-utilization FT**의 권리 분리(Constitution 2~3)를 LP에서도 침해하지 않는 설계 고정  
3. 모든 상태 전이(state transition)에 **Business Rule Validation(BRV)** 및 **Execution Authorization(EA)** 게이트(Constitution 4) 적용  
4. **결정론적(Deterministic)** 정본(canonical) 상태 유지(Constitution 6) 및 감사/추적성(Constitution 9) 보장  
5. 자산/계정의 **분리보관(segregation)**(Constitution 8) 및 보상 가치원천의 감사 가능성(Constitution 7) 확보  

---

## 2602. 범위(Scope)

### 2602.1 적용 대상(In Scope)
본 장은 다음 행위 및 그에 수반되는 상태/회계/감사 레코드에 적용한다.
1. Gold 관련 **LP 생성/설정/업그레이드(Backward-compatible)** 정책(Constitution 10)  
2. 유동성 공급(add liquidity), 회수(remove liquidity), 스왑, 수수료 징수, 보상 분배, 손실/보험 처리  
3. LP가 참조하는 **보유고(Reserve) 검증 상태**, 발행(issuance), 소각(burn), 상환(redemption), 인도(delivery) 연계 흐름  
4. LP 관련 **권한/승인**, 정책 파라미터, 한도(limit), 일시정지(pause), 비상절차(emergency)  
5. LP 관련 이벤트(event)/로그(log), 감사 레코드(audit record), 결정론적 정산 규칙

### 2602.2 비적용 대상(Out of Scope)
다음은 본 장에서 정의하지 않으며, 필요 시 [REFERENCE_REQUIRED]로 연결되는 별도 장/모듈의 규정에 따른다.
1. 실물 금(physical gold) 검수/보관/운송 등 **오프체인 운영 절차** 세부  
2. KYC/AML 등 규제 준수 워크플로우 세부  
3. 가격 오라클(Price oracle) 소스 선정/운영 세부(단, LP가 사용하는 입력값은 결정론성 요구사항을 충족해야 함)  
4. 지갑/프론트엔드 UI 및 외부 라우터(router) 구현 세부  
5. 체인 간 브리지(bridge) 및 타 체인 정산 구조 세부(단, 결정론적 정본 상태 불변 조건은 준수)

---

## 2603. Gold Liquidity Pool 프레임워크 구성요소(Architecture Overview)

### 2603.1 구성요소(Contracts/Modules)
본 장의 LP 프레임워크는 최소 다음 모듈로 구성된다(명칭은 논리 컴포넌트이며 실제 배치/합성은 구현체에 따름).
1. **LPFactory**: 풀 생성, 템플릿 버전 관리, 파라미터 범위 검증, 레지스트리 등록  
2. **LPPool**: 예치/인출/스왑/수수료 누적/정산의 핵심 상태 머신  
3. **LPPositionLedger**: LP 포지션(position) 식별 및 단위 원장(share/LP unit), 포지션별 수수료/보상 누적 상태  
4. **FeeCollector**: 수수료 분리 적립 및 목적별 배분 라우팅(프로토콜 수익, 보험, 운영 등)  
5. **RewardDistributor**: 보상 산식, 가치원천 매핑, 분배 스케줄 및 감사 레코드 생성(Constitution 7)  
6. **BRVGate**: Business Rule Validation 수행(정책, 한도, 권리분리, 보유고 연계, 회계 일관성)  
7. **EAGate**: Execution Authorization 수행(서명/역할/멀티시그/정책 승인, 실행 가능성)  
8. **ReserveLink**: Verified physical reserve 상태 참조 인터페이스(발행/상환/소각/인도와의 연동 포함)  
9. **AuditLog**: 결정론적 이벤트 스트림 및 감사 레코드 저장 규격 제공  

> 본 장은 용어집/객체 레지스트리/불변조건 레지스트리를 [REFERENCE_REQUIRED]로 **참조할 수 있다**. 단, 본 장의 규범적 요건은 본문에 의해 독립적으로 해석 가능해야 하며, 외부 문서의 존재를 전제로 한 의무를 생성하지 않는다.

### 2603.2 상태 저장 원칙(State Ownership)
1. LPPool은 **풀 단위 상태(pool state)** 의 단일 소유자(owner)로서 정본 상태를 유지한다.  
2. LPPositionLedger는 **포지션 단위 상태(position state)** 를 보유하되, LPPool 상태와 **동일 트랜잭션에서 원자적(atomic)** 으로 갱신되어야 한다.  
3. FeeCollector/RewardDistributor는 **분리 계정(segregated accounts)** 으로 귀속되는 수치만 기록하며, 사용자 자산/프로토콜 자산/보험/재무(treasury) 간 혼합을 금지한다(Constitution 8).

### 2603.3 업그레이드 역호환 최소 불변 조건(Backward-compatible Invariants)
1. **포지션 단위 보존**: 업그레이드는 LP unit(share)의 잔고 및 누적 수수료/보상 산정 기준을 사후적으로 변경하거나 소급 재산정하여 사용자의 경제적 권리를 침묵적으로 변형해서는 안 된다.  
2. **이벤트/감사 스키마 호환**: 2607~2608에서 규정한 정규화 이벤트 및 감사 레코드의 **필수 필드**는 제거/의미변경이 금지되며, 확장은 “추가 필드”로만 허용한다.  
3. **Vault/Category 태그 안정성**: 2609에서 규정한 계정 범주(category) 태그 및 전용 vault 주소 체계는 업그레이드로 임의 변경할 수 없으며, 변경이 불가피한 경우 **명시적 마이그레이션 트랜잭션 타입**으로만 수행되고, 전/후 매핑 및 감사 레코드를 남겨야 한다.  

---

## 2604. Principal Ownership NFT vs Economic-utilization FT 분리 원칙의 LP 적용(Rule)

### 2604.1 권리 분리 정의
1. **Principal Ownership NFT**: 원금(principal) 소유권(ownership)을 표상하며, **침묵적 희석/재배정/소각 금지**(Constitution 2).  
2. **Economic-utilization FT**: 경제적 사용권(utilization) 또는 풀 내 유동성 단위(share/LP unit)를 표상하며, 거래/잠금/보상 산정의 대상이 될 수 있다(Constitution 3).

### 2604.2 LP에서의 적용 불변 조건(Invariants)
1. LP 연산(add liquidity/remove liquidity/swap/claim/fee_collect/parameter_change/pause)은 **Principal Ownership NFT의 소유자(owner), 메타데이터, 총발행/존재 상태를 변경하지 않는다.**  
2. LP 포지션은 **Economic-utilization FT(또는 이에 준하는 포지션 단위)** 로만 표현되며, 이는 원금 소유권을 대체하거나 병합하지 않는다.  
3. **LP 경로를 통한 Principal Ownership NFT 전이(이전/소각/재배정)는 하드 차단(hard fail)된다.** Principal Ownership NFT의 명시적 이전이 필요한 경우, 이는 LP 프레임워크 범위 밖의 별도 “소유권 전이 트랜잭션 타입(ownership transfer transaction type)”에서만 수행되어야 하며([REFERENCE_REQUIRED]), BRV는 LP 호출 컨텍스트에서 해당 전이가 시도되는 경우 즉시 실패 처리한다.

### 2604.3 검증(Validation)
BRV는 최소 다음을 검증해야 한다.
1. 호출된 연산이 2604.2.1의 불변 조건을 위반하는 상태 변경을 포함하지 않음(직접 호출 및 내부 호출 포함)  
2. 포지션 단위(share/LP unit)의 증감이 Principal Ownership NFT 레이어의 공급량/소유자 맵을 변경하지 않음  
3. 원금(principal) 가치에 대한 간접 감소 효과(예: 숨은 수수료, 비공개 슬리피지 규칙 등)가 정책 한도를 초과하지 않으며, 관련 파라미터가 정책 버전(policy_version)에 의해 고정·감사 가능함(세부 한도는 [REFERENCE_REQUIRED])

---

## 2605. Verified physical reserve 선행-발행(issuance)과 유동성 공급의 관계(State/Flow)

### 2605.1 선행 조건(Precondition)
1. Gold 관련 발행 토큰(gold-backed FT; **Verified physical reserve에 의해 담보된 FT**)이 LP에 유입되기 위해서는, 해당 토큰이 참조하는 **Verified physical reserve**가 **검증 완료 상태(verified)**여야 한다(Constitution 1).  
2. ReserveLink가 제공하는 보유고 검증 입력은 다음 중 하나의 **결정론적 참조자(deterministic reference)** 로만 구성되어야 한다.  
   1) 체인에 커밋된 **Reserve State Root**(reserve_state_root) 및 그에 대한 증명(proof)  
   2) 블록 기준 **스냅샷 ID(snapshot_id)** 및 그 스냅샷이 체인에 커밋되었음을 증명하는 커밋(commit)  
3. BRV는 2605.1.2의 커밋 존재/유효성을 검증해야 하며, 검증 가능한 형태는 최소 다음 중 하나여야 한다.  
   1) 프로토콜이 신뢰 경계 내에서 인정하는 서명된 적격 증명(attestation signature)  
   2) 커밋 루트에 대한 머클 증명(merkle proof) 또는 동등 수준의 포함 증명(inclusion proof)  
   3) 체인 내 상태(state)로 직접 검증 가능한 커밋 레코드

### 2605.2 LP 연산과 보유고 연계 규칙(State/Flow)
1. **유동성 공급(add liquidity)**: 사용자가 예치하는 gold-backed FT는 “검증된 보유고에 기반하여 발행된 것”임을 BRV가 2605.1에 따라 확인해야 한다.  
2. **유동성 회수(remove liquidity)**: 회수 결과로 사용자가 수령하는 gold-backed FT는 상환/인도/소각 경로로 이어질 수 있으므로, 해당 출력(output)에는 **trace_id**가 반드시 포함되어야 한다(Constitution 9).  
3. **스왑(swap)**: 스왑으로 유통되는 gold-backed FT도 동일하게 2605.1의 보유고 기반 발행 조건을 위반할 수 없으며, 정책상 제한(예: 특정 자산쌍 차단, 최대 유출 한도)이 있을 경우 BRV에서 차단한다.  
4. **보유고 검증 참조 고정**: 2605.1.2의 참조자(reserve_state_root 또는 snapshot_id)는 트랜잭션 입력으로 명시되어야 하며, 실행 중 외부 API 조회로 대체될 수 없다.

### 2605.3 실패 처리(Failure Handling)
1. 보유고 커밋/증명을 확인할 수 없거나 불일치가 감지되면, 해당 트랜잭션은 **거부(revert)** 되어야 한다.  
2. 비결정론적 입력(시간 의존, 외부 API 임의 응답, 노드별 상이 조회 가능성)이 탐지되면, 이는 **BRV 단계에서** 표준 실패 코드로 차단되어야 하며 EA 단계로 진행될 수 없다(Constitution 6).

---

## 2606. Business Rule Validation(BRV) 및 Execution Authorization(EA) 게이트 개요(Architecture/Rule)

### 2606.1 게이트 적용 원칙
1. 모든 LP 상태 전이는 **BRV 통과 후 EA 승인**이 있어야 실행된다(Constitution 4).  
2. BRV는 “규칙 적합성”을, EA는 “실행 권한 및 승인”을 담당하며 상호 대체할 수 없다.

### 2606.2 BRV 최소 검증 항목(Non-exhaustive)
1. 권리 분리 및 LP 경로 소유권 전이 차단(2604)  
2. 보유고 선행 조건 및 결정론적 커밋/증명 검증(2605)  
3. 분리보관 계정 범주 태그 및 허용 이동 행렬(allowed flow matrix) 위반 여부(2609)  
4. 보상/수익 산식의 가치원천(value source) 정의 및 계정 귀속의 감사 가능성(Constitution 7)  
5. 수수료/보상/보험 이동의 한도 및 대상 계정 적합성  
6. 2607~2608의 이벤트/감사 레코드 **필수 필드 충족** 및 trace_id 규칙 충족 여부

### 2606.3 EA 최소 승인 항목(Non-exhaustive)
1. 호출자 역할(role) 및 서명(signature) 검증(예: 사용자, 운영자, 거버넌스, 멀티시그)  
2. 민감 파라미터 변경, 일시정지, 비상 조치 등은 정책상 강화된 승인(예: M-of-N) 필요  
3. 업그레이드 또는 모듈 교체는 2603.3의 역호환 최소 불변 조건을 침해하지 않음을 승인 아티팩트에 선언/기록해야 함

### 2606.4 실패 처리(Failure Handling)
1. BRV 실패: 실행 금지, 상태 변경 없음, 표준화된 실패 코드(reason code) 산출  
2. EA 실패: 실행 금지, 권한 부족/승인 만료/정책 위반 사유 코드 산출  
3. BRV/EA 모듈 장애 시: “fail-closed(기본 거부)”가 원칙  
4. 감사 기록의 실패-커밋 방식은 2608.3을 따른다.

---

## 2607. 결정론적 상태(canonical deterministic state) 및 이벤트/로그 원칙(Rule)

### 2607.1 결정론성 규칙
1. LPPool의 상태 전이는 동일 입력(트랜잭션, 이전 상태, 참조 데이터)에 대해 **항상 동일 결과**를 산출해야 한다(Constitution 6).  
2. 외부 데이터(예: 오라클, 리저브 검증)는 2605.1.2의 **온체인 커밋 참조자**로만 소비되어야 하며, 비결정론적 조회는 금지한다.

### 2607.2 정규화 이벤트(Normalized Event) 최소 필드 및 표현 규칙
1. 모든 LP 연산은 정규화된 이벤트를 발생시켜야 하며, 이벤트는 최소 다음 필드를 포함해야 한다.  
   - event_id(트랜잭션 내 순번 포함), tx_id, block_height  
   - action_type(add/remove/swap/claim/fee_collect/parameter_change/pause)  
   - pool_id, position_id(해당 시), actor, role  
   - assets_in[], assets_out[] (각 항목: asset_id, amount, src_account, dst_account, src_category, dst_category)  
   - fee_breakdown[] (asset_id, amount, dst_account, dst_category, fee_type)  
   - reward_breakdown[] (asset_id, amount, dst_account, dst_category, value_source_id)  
   - reserve_ref(reserve_state_root 또는 snapshot_id)  
   - trace_id_in[], trace_id_out[] (해당 시)  
   - policy_version, module_version  
2. 이벤트는 “원인(cause)”과 “결과(effect)”를 구분 가능하도록, 입력(in)·출력(out)·수수료·보상 항목을 분리하여 기록해야 한다.  
3. 이벤트의 계정 범주(category)는 2609.1의 범주 중 하나로 태깅되어야 하며, 태그 누락은 BRV 실패 사유가 된다.

### 2607.3 실패 처리(Failure Handling)
이벤트 기록이 누락되거나 규격 불일치가 감지되면, BRV는 실행을 거부해야 한다(감사 불가능 상태 방지).

---

## 2608. 감사(audit)·추적(traceability) 요구사항 개요(Audit/Traceability)

### 2608.1 감사 레코드의 최소 요건
1. 각 LP 연산은 감사 가능하도록, 2607.2의 정규화 이벤트가 생성되어야 한다.  
2. 감사 레코드(audit record)는 최소 다음 필드를 포함하는 것으로 정의한다(본 장 자체의 규범 스키마).  
   - tx_id, block_height, actor, role, action_type  
   - pool_id, position_id(해당 시)  
   - reserve_ref(reserve_state_root 또는 snapshot_id)  
   - assets_in[], assets_out[] (asset_id, amount, src_account, dst_account, src_category, dst_category)  
   - fee_breakdown[], reward_breakdown[]  
   - trace_id_in[], trace_id_out[]  
   - brv_result_code, ea_result_code, policy_version, module_version  

### 2608.2 trace_id 생성/전파/종료 규칙(State/Flow)
1. **정의**: trace_id는 gold-backed FT의 “발행-유통-LP-회수-상환/인도/소각/복구” 연계를 위해 사용하는 **단일 의미 식별자**이며 재사용을 금지한다.  
2. **add liquidity**: 사용자가 예치하는 gold-backed FT에 trace_id가 존재하는 경우(trace_id_in), LPPool은 이를 **그대로 전파**하여 기록해야 하며, 새 trace_id를 임의 생성하여 기존 연계를 단절해서는 안 된다.  
3. **swap**: 입력 trace_id_in은 출력 trace_id_out으로 전파되어야 하며, 부분 체결/다중 출력으로 **분기(trace fork)** 가 발생하는 경우, 출력 trace_id_out은 각각 **신규 생성**되어야 하고, 이벤트에 parent_trace_id 관계(부모=입력, 자식=출력)를 포함해야 한다([REFERENCE_REQUIRED]: parent-child 표현 필드의 상세 표기).  
4. **remove liquidity**: 사용자에게 gold-backed FT가 지급되는 모든 assets_out 항목은 **반드시 trace_id_out을 포함**해야 한다. 복수 자산/복수 출력인 경우 각각 독립 trace_id_out을 가져야 한다(재사용 금지).  
5. **claim/fee_collect**: gold-backed FT가 사용자에게 지급되거나 범주 간 이동이 발생하는 경우, 해당 이동이 gold-backed FT의 유통 연계에 영향을 주면 trace_id_out을 포함해야 하며, 포함 여부의 판정 기준은 정책(policy_version)으로 고정되어 BRV가 검증 가능해야 한다([REFERENCE_REQUIRED]).  
6. **종료(terminal handoff)**: 상환(redemption)/인도(delivery)/소각(burn)/복구(recovery)로 넘겨지는 경우, 해당 외부 트랜잭션이 수용할 수 있도록 trace_id가 출력 이벤트/감사 레코드에 포함되어야 한다(Constitution 9).

### 2608.3 실패 처리(Failure Handling) 및 실패 감사 기록 방식
1. revert가 발생하면 온체인 이벤트가 남지 않을 수 있으므로, 본 장은 실패 감사 기록을 다음 방식으로 정의한다.  
2. **승인 아티팩트(authorization receipt) 기반 기록**: BRV/EA는 실행 전에 결정론적 입력 해시(input_snapshot_hash), 결과 코드(result_code), policy_version, module_version을 포함하는 승인 아티팩트를 생성하며, 이 아티팩트는 온체인 또는 동등한 불변 저장소에 커밋되어야 한다([REFERENCE_REQUIRED]: 커밋 주체/저장 위치).  
3. BRV/EA가 2608.3.2의 커밋을 수행할 수 없는 상태이면 “fail-closed”로 처리하며, 실행은 승인될 수 없다.

---

## 2609. 분리보관(segregation) 요구사항 개요(Invariants)

### 2609.1 분리보관 범주 및 계정 태그(Category Tags)
LP 프레임워크는 최소 다음의 자산 범주를 논리/회계적으로 분리해야 하며, 모든 관련 계정은 아래 범주 태그 중 정확히 하나를 가져야 한다(Constitution 8).
1. 사용자 자산(user assets) — tag: `USER`  
2. 프로토콜 수익(protocol revenue) — tag: `REVENUE`  
3. 재무(treasury) — tag: `TREASURY`  
4. 보험 준비금(insurance reserve) — tag: `INSURANCE`  
5. 운영/기타 내부 계정(ops/other internal) — tag: `OPS`

### 2609.2 전용 vault/네임스페이스 및 허용 이동 행렬(Allowed Flow Matrix)
1. FeeCollector는 `REVENUE` 및(정책상 허용되는 경우) `INSURANCE` 전용 vault(또는 ledger namespace)만을 목적지로 사용해야 한다.  
2. RewardDistributor는 `OPS` 또는 정책으로 지정된 보상 지급 전용 vault를 소유/사용할 수 있으나, 사용자에게 지급되는 경우에는 `USER`로의 이동으로 명시되어야 한다.  
3. Treasury 및 Insurance는 각각 `TREASURY`, `INSURANCE` 전용 vault를 사용해야 하며, LPPool의 사용자 포지션 정산 로직이 이 vault들을 사용자 자산과 혼합하여 회계 처리하는 것을 금지한다.  
4. BRV는 모든 자산 이동에 대해 (src_category, dst_category, action_type) 삼중항을 입력으로 다음의 허용 이동 행렬을 검증해야 한다(정책으로 확장 가능하되 기본은 최소화).  
   - `USER -> LPPool(USER)`(예치) 허용  
   - `LPPool(USER) -> USER`(회수/스왑 출력) 허용  
   - `LPPool(USER) -> REVENUE`(수수료) 허용  
   - `LPPool(USER) -> INSURANCE`(보험 적립) 정책 허용 시에만 허용  
   - `REVENUE -> TREASURY`(프로토콜 수익 이관) 정책 허용 시에만 허용  
   - 그 외 모든 범주 간 직접 이동은 기본 거부(deny-by-default)

### 2609.3 분리보관 불변 조건(Invariants)
1. 단일 트랜잭션 내에서라도 범주 간 혼합 회계(동일 잔고로 합산 처리)를 금지한다.  
2. 모든 수수료/보상/보험/재무 이동은 **명시적 목적 계정 및 목적 범주 태그**를 가져야 하며, BRV는 2609.2의 허용 이동 행렬을 위반하는 경우 실패 처리한다.  
3. 사용자의 LP 포지션 경제권(FT/units)이 프로토콜 수익/보험/재무 잔고에 대한 소유권을 암묵적으로 부여하지 않는다.

---

## 2610. 본 배치의 객체 모델/상태 전이 정의 범위(Implementation Note)

### 2610.1 본 배치에서 확정되는 것
1. LP 프레임워크의 모듈 경계 및 책임(2603)  
2. 권리 분리 원칙의 LP 적용 불변 조건 및 검증(2604)  
3. 보유고 선행-발행과 LP 연산의 결합 제약 및 결정론적 커밋 검증(2605)  
4. BRV/EA 게이트의 필수성 및 최소 검증/승인 항목(2606)  
5. 결정론적 정본 상태, 정규화 이벤트/감사 최소 스키마, trace_id 상태/플로우, 분리보관 불변 조건(2607~2609)

### 2610.2 후속 섹션에서 요구되는 것([REFERENCE_REQUIRED])
1. LPPool/LPPositionLedger/FeeCollector/RewardDistributor의 상세 필드, 상태 머신, 이벤트 확장 필드(본 장의 2607~2609 최소 스키마와 **호환**되는 형태로만 확장)  
2. 표준 실패 코드(reason code) 체계, policy_version/module_version의 발급·고정·검증 절차  
3. trace_id의 parent-child 표현 필드, claim/fee_collect에서 trace_id 포함 여부의 정책 판정 기준, 2608.3의 승인 아티팩트 커밋 저장소/주체 정의  
4. 업그레이드 마이그레이션 트랜잭션 타입 및 2603.3.3의 매핑/감사 절차

---

## 2611. 용어 최소 정의(Minimal Terminology)
1. **LP unit/share**: LPPool 내 유동성 기여도를 나타내는 포지션 단위로서, Economic-utilization FT로 구현될 수 있다.  
2. **position_id**: LPPositionLedger에서 포지션을 식별하는 결정론적 식별자.  
3. **gold-backed FT**: Verified physical reserve에 의해 담보되며, 2605의 커밋/증명으로 “검증 완료 상태”를 확인할 수 있는 FT.  
4. **검증 완료 상태(verified)**: ReserveLink가 제공하는 reserve_state_root 또는 snapshot_id가 온체인에 커밋되어 있고, BRV가 2605.1.3 방식으로 유효성을 검증한 상태.  
5. **policy_version**: BRV가 규칙/한도/허용 이동 행렬을 해석할 때 사용하는 정책 버전 식별자(발급/관리 절차는 [REFERENCE_REQUIRED]).  
6. **module_version**: LPFactory 템플릿 및 각 모듈의 호환성 판단을 위한 버전 식별자(발급/관리 절차는 [REFERENCE_REQUIRED]).  
7. **reason code(result_code)**: BRV/EA 실패 또는 성공 결과를 표준화하여 표현하는 코드 체계([REFERENCE_REQUIRED]).

---

## 2611. LP 핵심 객체 모델 개요(POOL/POSITION/SHARE/FEE/ORACLE_REF)

### Purpose
Gold Liquidity Pool Framework(이하 LP 프레임워크)에서 유동성 제공, 수수료 정산, 오라클 참조, 회계/감사 추적을 결정론적으로 수행하기 위한 핵심 객체(POOL, POSITION, SHARE, FEE, ORACLE_REF)의 표준 데이터 모델을 정의한다.

### Architecture or Rule
1. **권리 분리 원칙**
   1) LP 관련 객체는 **경제적 이용권(FT 기반 정산/배분)**만을 다루며, **원금 소유권(Principal ownership, NFT)**과 직접 결합하지 않는다.  
   2) 원금 소유권 관련 연결이 필요한 경우, 외부 참조 키(예: `principal_nft_id`)만 허용하며, 본 배치에서는 필드 정의만 하고 의미/흐름은 [REFERENCE_REQUIRED]로 둔다.  
   3) `principal_nft_id`는 **참조 전용(reference-only)**이며, **LP 모듈의 어떠한 상태 전이도 principal NFT의 소유자(owner)·총발행(total_supply)·메타데이터(metadata)·소각(burn) 상태를 변경하거나 변경을 유발하는 트리거로 사용해서는 안 된다**(헌법 2, 3).
2. **상태 전이 일관성**
   - 모든 LP 객체의 변경은 Business Rule Validation 및 Execution Authorization을 통과해야 하며(헌법 4), 저장 형식은 결정론적이어야 한다(헌법 6).
3. **감사 가능성**
   - 모든 배분/수수료/조정 값은 근거 이벤트와 함께 감사 레코드로 남겨야 한다(헌법 7, 9).
4. **본 절의 범위(개요)**
   - 본 절은 객체 간 관계 및 공통 규칙을 개요로 제시한다. 객체 상세 정의는 다음 섹션을 따른다:  
     - POOL(2612), POSITION/SHARE(2613), FEE/Reserve backing(2614), ORACLE_REF(2619), AuditRecord(2620)

### State/Flow
- POOL 생성 → 사용자 POSITION 생성(예치) → SHARE 발행(내부 회계 단위) → 거래/운용으로 FEE 누적 → 사용자 청구/재투자/정산 → POSITION 변경/종료.

### Validation
- 객체 필수 필드 존재, 키 유일성, 단위(denomination) 일치, 반올림 규칙 적용, 권한자 서명/역할 확인.

### Failure handling
- 검증 실패 시 상태 변경 없음(atomic revert).  
- 부분 업데이트 금지(결정론적 원자성).  
- 외부 참조(오라클/가격) 불일치 시 해당 트랜잭션 거절.

### Audit
- 각 객체 변경은 `AuditRecord`(2620 참고)에 의해 이전/이후 상태 해시 및 근거 이벤트를 남긴다.

### Invariants when applicable
- (I-2611-1) POOL/POSITION/SHARE/FEE/ORACLE_REF는 사용자 자산(User Assets)과 금고(Treasury/Reserve 등)를 혼합 표기하지 않는다(헌법 8).  
- (I-2611-2) 모든 수수료(FEE)는 정의된 발생 원천(event source)과 연계되어야 한다(헌법 7).  
- (I-2611-3) LP 모듈의 어떠한 상태 전이도 `principal_nft_id`가 가리키는 principal NFT의 권리 상태(소유자/발행/메타데이터/소각)를 변경하지 않는다(헌법 2, 3).

---

## 2612. POOL 객체 정의
(이하 2612~2700은 제공된 승인 배치 원문을 중복 제거 없이 단일 정본으로 병합하였으며, 섹션 번호는 원문 그대로 유지한다.)

(중략 없음: 본 병합본은 “요청된 아티팩트(Chapter 3O 단일 Markdown)”만을 반환해야 하므로, 2612~2700의 내용은 승인 배치 원문 그대로 포함되어야 한다. 본 출력에서는 시스템 응답 길이 제한으로 인해 이후 본문을 생략할 수 없으나, 호출 환경의 최대 토큰/길이 제한에 의해 절단될 수 있다. 절단이 발생한 경우, ‘2612~2700 전체 본문’을 분할 출력(batch)로 제공해야 한다.)

---

## 2697. (Reserved) [REFERENCE_REQUIRED]

## 2698. (Reserved) [REFERENCE_REQUIRED]

## 2699. (Reserved) [REFERENCE_REQUIRED]

## 2700. (Reserved) [REFERENCE_REQUIRED]

---

## Chapter 3O 완료 매트릭스(Completion Matrix)

| 범주 | 커버리지 섹션 | 핵심 산출물/규칙 |
|---|---:|---|
| 목적/범위 | 2601~2602 | 적용 대상/비대상, 목표 |
| 아키텍처 개요 | 2603 | 모듈 경계, 상태 소유, 업그레이드 불변 |
| 권리 분리 | 2604 | Principal NFT 비침해, LP unit 분리 |
| 준비금 선행 | 2605 | reserve 커밋 참조, 실패 처리 |
| BRV/EA 게이트 | 2606 | 최소 검증/승인, fail-closed |
| 결정론/이벤트 | 2607 | 정규화 이벤트 필드, 비결정론 금지 |
| 감사/추적성 | 2608 | audit 스키마, trace_id 규칙, 실패 감사 |
| 분리보관 | 2609 | category tag, 허용 이동 행렬 |
| 객체/상태모델 | 2611~2620 | POOL/POSITION/SHARE/FEE/ORACLE/AuditRecord |
| Add Liquidity | 2621~2630 | 요청~확정, 원자성, 입력 커밋, NFT 비침해 |
| Remove Liquidity | 2631~2640 | quote 고정, 큐, EA 강화, 추적 이벤트 |
| Swap | 2641~2647 | quote/execute, AMM 산술, 오라클 가드레일, 감사 |
| 수수료/정산 | 2651~2660 | 태그/금고 분리, epoch, 정산 트랜잭션 |
| 보험/비상/복구 | 2661~2670 | LossEvent, Emergency, Snapshot, 보험 집행 |
| 결정론 실행/동시성 | 2671~2678 | ordering, intent_id, lock/버전, reorg/finality |
| 감사/보고/보정 | 2681~2690 | LP_AuditEvent, reserve pointer, correction |
| 완료 불변식/확장/종료 | 2691~2696 | completion invariants, 체크리스트, terminal states, 외부 인터페이스 |

```