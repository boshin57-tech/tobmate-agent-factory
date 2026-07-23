# Chapter 3O — Gold Liquidity Pool Framework

<-bash: cd: /home/boshin57/tobmate-agent-factory: No such file or SOURCE: workspace/drafts/3O_2601_2610_approved.md -->
```markdown
## 2601. Chapter 3O — Gold Liquidity Pool Framework(GLPF) 목적 및 범위(Scope)

### 2601.1 Purpose
본 Chapter 3O — Gold Liquidity Pool Framework(GLPF)의 목적은 Chapter 3N에서 확립된 헌법 계층(Constitutional Layer)의 불변 조건을 변경하지 않고, 경제 계층(Economic Layer)에서 실행 가능한 유동성 프로토콜(Liquidity Protocol)을 객체 모델(Object Model)과 상태기계(State Machine)로 명세하는 데 있다.

### 2601.2 Architecture or Rule
1. GLPF는 다음 실행 순서를 전제(Precondition)로 하며, 이 순서는 어떠한 구현에서도 재배열될 수 없다.
   1) Verified Reserve  
   2) Protected Ownership  
   3) Authorized Execution  
   4) Consensus  
   5) Liquidity  
   6) Revenue Generation  
   7) Revenue Distribution  
   8) Treasury Growth  
   9) Sustainable Ecosystem
2. GLPF는 원금 소유권 NFT(Principal Ownership NFT)와 경제적 활용 FT(Economic Utilization FT)의 권리 분리를 유지한다.
3. GLPF의 모든 상태 전이(State Transition)는 Business Rule Validation(BRV) 및 Authorization Validation(EA)을 선행 통과해야 한다. (BRVF/EAF 상세는 [REFERENCE_REQUIRED])
4. GLPF 연산은 원금 소유권 NFT(Principal Ownership NFT)에 대해 “참조(reference)만 허용”하며, 어떠한 직접 변이(mutation)도 금지한다. 변이 금지 범위는 2604.2의 Ownership Invariant Check에 의해 강제된다.

### 2601.3 State/Flow
- 입력(Input): 준비금 검증 완료 상태(Verified Reserve State), 소유권 보존 상태(Ownership Preserved State), 승인된 실행 권한(Authorized Execution)
- 처리(Process): Liquidity Pool 생성/유동성 추가/유동성 제거/스왑/수수료 정산/수익 분배/재무(Treasury) 반영
- 출력(Output): 결정론적 원장 갱신(Deterministic Ledger Update) 및 불변 감사 기록(Immutable Audit Record)

### 2601.4 Validation
- 모든 트랜잭션은 다음 검증 체인을 만족해야 한다.
  - Constitution Validation → Business Rule Validation → Authorization Validation(EA) → Consensus Validation → Ledger Commit → Audit Recording
- 검증 실패 시 합의(Consensus)는 해당 상태 제안(State Proposal)을 거부(REJECT)한다.

### 2601.5 Failure handling
- BRV 실패: 실행 중단(Execution Stops), 상태 변경 없음, 실패 사유 코드 기록
- EA 실패: 실행 중단, 권한 부족(Unauthorized)으로 기록
- Consensus 실패: 미확정(Unfinalized) 처리, 원장 커밋 금지

### 2601.6 Audit
- 모든 경제 이벤트는 최소 다음 필드를 포함하는 감사 레코드(Audit Record)를 생성해야 한다.
  - `tx_hash`, `actor`, `action_type`, `object_ids[]`, `pre_state_hash`, `post_state_hash`, `rule_set_id`, `rule_set_hash`, `auth_context_id`, `timestamp`, `result_code`
  - `correlation_id` (redemption/burn/settlement/recovery 연계 추적을 위한 상관 식별자; 상세 체계는 [REFERENCE_REQUIRED])
- 버전/규칙/레지스트리 식별자는 노드별 해석 차이를 금지하기 위해 온체인 레지스트리 객체(on-chain registry object)의 `*_id` 및 `*_hash`로 고정되어야 한다. (레지스트리 객체 정의는 [REFERENCE_REQUIRED])

### 2601.7 Invariants
1. Verified physical reserve must precede issuance (준비금 선행)
2. Principal ownership must not be silently diluted, reassigned, or destroyed (원금 소유권 무단 변형 금지)
3. Ownership NFT와 Utilization FT는 별도 권리로 유지 (권리 분리)
4. Every state transition must pass Business Rule Validation and Execution Authorization (검증/권한 선행)
5. Canonical ledger state must remain deterministic (결정론 원장 불변)
6. Every economic reward must correspond to a defined and auditable value source (감사 가능한 가치원 귀속)
7. Treasury/Insurance/Protocol Revenue/User Assets의 분리 회계가 유지되어야 함 (Segregation)
8. No liquidity operation may bypass reserve, ownership, consensus, or audit invariants (유동성 연산 우회 금지)
9. Physical delivery, redemption, burn, settlement, and recovery는 연계 추적 가능해야 하며, GLPF는 이를 위한 `correlation_id` 제공을 요구한다(추적성 훅).


## 2602. 비범위(Non-Scope) 및 외부 의존성(Dependencies)

### 2602.1 Purpose
GLPF가 다루지 않는 범위(Non-Scope)를 명시하여, 헌법 계층 및 타 프레임워크와의 경계를 고정한다.

### 2602.2 Architecture or Rule
1. 본 배치(2601~2610)는 “목적·범위 및 헌법 상속 선언”에 한정되며, AMM 수학 모델, 풀 수수료 함수, 세부 Move 모듈 인터페이스는 후속 절에서 정의한다. ([REFERENCE_REQUIRED])
2. 다음 항목은 본 배치의 비범위로 선언한다.
   1) 준비금 검증 로직의 상세(Reserve verification internals) — GRBF 영역
   2) 물리적 인출/배송(Physical delivery) 상세 — PDBRF 영역
   3) 거버넌스 투표/제안 시스템 상세 — DAO Governance Framework 영역
   4) 체인 합의 알고리즘 상세 — Consensus Layer 영역
3. 본 배치(2601~2610)에서는 토큰 발행/소각(issuance/mint/burn)을 GLPF의 범위에 포함하지 않는다. 유통량 변화가 필요한 경우 해당 기능은 별도 프레임워크/모듈에서 정의되어야 하며, 그 참조는 [REFERENCE_REQUIRED]로 둔다.

### 2602.3 State/Flow
- GLPF는 “Verified Reserve State”와 “Ownership Preserved State”를 전제 조건으로 입력받으며, 이를 생성하는 절차는 외부 프레임워크가 담당한다.

### 2602.4 Validation
- 외부 의존 상태의 참조는 반드시 상태 해시/버전(예: `reserve_state_hash`, `ownership_state_hash`)로 고정되어야 하며, 런타임 조회 결과가 노드별로 달라질 수 있는 비결정적 호출을 금지한다.
- 본 문서에서 사용되는 모든 `*_version`/`*_id`는 “온체인 레지스트리 객체”의 `id + hash` 조합으로 고정되어야 하며, 문자열/로컬 구성에 의한 버전 해석을 금지한다. (레지스트리 객체는 [REFERENCE_REQUIRED])

### 2602.5 Failure handling
- 외부 상태 참조 불일치(해시 불일치) 발생 시: 트랜잭션 거부, 감사 레코드에 `DEPENDENCY_STATE_MISMATCH` 기록

### 2602.6 Audit
- 의존성 참조 필수 필드:
  - `dependency_type`, `dependency_object_id`, `dependency_state_hash`, `dependency_version_id`, `dependency_version_hash`

### 2602.7 Invariants
- 경제 계층은 준비금/소유권 계층을 우회하거나 대체할 수 없다.
- 외부 의존은 결정론적 식별자(IDs) 및 해시 기반 참조만 허용한다.


## 2603. 경제 계층 전환 원칙(Economic Layer Transition Principle)

### 2603.1 Purpose
헌법 계층에서 경제 계층으로의 전환이 “원칙 추가”가 아니라 “원칙의 실행 가능화(Executable Formalization)”임을 명세한다.

### 2603.2 Architecture or Rule
1. 전환 헌장(Transition Charter):
   - Constitution → Protocol → Framework → Object Model → State Machine → Move Modules → Economic Services
2. 경제 서비스(Economic Services)는 헌법적 속성(Constitutional Properties)을 자동 상속하며 선택 사항이 아니다.

### 2603.3 State/Flow
- 경제 계층의 모든 작업(예: Liquidity Add/Remove, Swap, Fee Accrual)은 동일한 상속 체인을 통해 “검증 가능 입력(Verified Inputs) → 승인된 실행(Authorized Execution) → 합의 확정(Consensus Finality) → 감사 기록(Audit)” 흐름을 따른다.

### 2603.4 Validation
- 상속 위반(예: BRV/EA 없이 상태 변경 시도)은 “Constitution Validation FAIL”로 분류되어 합의에서 배제되어야 한다.

### 2603.5 Failure handling
- `CONSTITUTION_INHERITANCE_VIOLATION` 코드로 즉시 중단 및 거부 처리

### 2603.6 Audit
- 상속 매트릭스/헌법/프레임워크 식별 필드(해시 기반 고정):
  - `inheritance_matrix_id`, `inheritance_matrix_hash`
  - `constitution_version_id`, `constitution_version_hash`
  - `framework_version_id`, `framework_version_hash`
- 상기 식별자는 온체인 레지스트리 객체 참조로만 정의된다. (레지스트리 객체는 [REFERENCE_REQUIRED])

### 2603.7 Invariants
- 경제 계층은 헌법을 변경할 수 없으며, 변경 없이 구현만 수행한다.


## 2604. 헌법 상속 매트릭스(Constitutional Inheritance Matrix) — GLPF 적용

### 2604.1 Purpose
GLPF가 자동 상속해야 하는 헌법적 불변 조건을 “검증 항목(Validation Checklist)”로 변환한다.

### 2604.2 Architecture or Rule
GLPF의 모든 상태 전이는 아래 체크리스트를 통과해야 한다. 각 `check_type` 값은 불변식 레지스트리(invariant registry)의 키와 동일해야 하며, 레지스트리 정의는 [REFERENCE_REQUIRED]로 둔다.

1. Reserve Invariant Check (`check_type = RESERVE_VERIFIED`)
   - 준비금 검증 상태가 존재하며 유효해야 한다(Verified Reserve).
2. Ownership Invariant Check (`check_type = OWNERSHIP_NO_MUTATION`)
   - GLPF 연산은 원금 소유권 NFT(Principal Ownership NFT)에 대해 다음을 모두 금지한다.
     - (a) mint 금지
     - (b) burn 금지
     - (c) 소유자(owner) 변경 금지
     - (d) 메타데이터/권리 속성(metadata/rights) 변경 금지
   - GLPF에서의 소유권 참조는 `ownership_state_hash`(및 그에 대응하는 `ownership_state_object_id`)로만 허용한다.
3. Authorization Invariant Check (`check_type = AUTHZ_REQUIRED`)
   - 실행 주체(Actor)와 실행 행위(Action)에 대응하는 권한이 Authorization Validation(EA) 컨텍스트에 의해 승인되어야 한다.
4. Determinism Invariant Check (`check_type = DETERMINISTIC_EXECUTION`)
   - 동일 입력에 대해 모든 노드가 동일 결과를 산출해야 한다.
5. Audit Invariant Check (`check_type = AUDIT_APPEND_ONLY_BINDING`)
   - 상태 전이와 동일 원인-결과를 갖는 감사 레코드가 생성되어야 하며, `post_state_hash`에 결합(binding)되어야 한다.
6. Segregation Invariant Check (`check_type = SEGREGATED_ACCOUNTS`)
   - Treasury/Insurance/Protocol Revenue/User Assets는 분리된 계정/저장소로 기록되어야 한다.
7. Value Source Invariant Check (`check_type = VALUE_SOURCE_MAPPED`)
   - 수익/보상은 정의된 수익원(Revenue Source)에 매핑되어야 한다.
8. No-Bypass Liquidity Check (`check_type = NO_BYPASS_INVARIANTS`)
   - 어떠한 유동성 연산도 reserve/ownership/consensus/audit 불변식을 우회할 수 없다.

### 2604.3 State/Flow
- `StateProposal` 생성 → 체크리스트 평가 → 통과 시에만 `ExecutableTransition`로 승격 → 합의 대상 포함

### 2604.4 Validation
- 체크리스트 평가 결과는 다음 필드를 포함하는 “검증 결과 객체(Validation Result)”로 직렬화되어야 한다.
  - `proposal_id`, `checks[] {check_type, pass, reason_code}`, `validator_set_hash`, `rule_set_id`, `rule_set_hash`, `framework_version_id`, `framework_version_hash`

### 2604.5 Failure handling
- 단일 체크 실패라도 전체 전이 실패(atomic fail) 처리
- Ownership 변이 탐지 시 표준 실패 코드:
  - `OWNERSHIP_MUTATION_DETECTED`
- 실패 사유는 `reason_code`로 표준화되어야 한다. (코드 체계는 [REFERENCE_REQUIRED])

### 2604.6 Audit
- 체크리스트 결과 해시(`validation_result_hash`)를 감사 레코드에 포함

### 2604.7 Invariants
- 체크리스트의 생략, 순서 변경, 조건 약화는 금지된다(Backward-compatible invariants).
- `check_type`는 레지스트리 키와 불일치할 수 없다([REFERENCE_REQUIRED]).


## 2605. 용어 정렬(Terminology Alignment) — GLPF 최소 집합

### 2605.1 Purpose
GLPF 문서 및 구현에서 혼용될 수 있는 핵심 용어를 최소 집합으로 정렬한다. 상세 용어집 및 코드 체계는 [REFERENCE_REQUIRED]로 둔다.

### 2605.2 Architecture or Rule
- Liquidity Pool: 두 개 이상의 자산(FT)을 예치하여 교환 및 수수료 축적을 수행하는 온체인 풀 객체
- AMM(Automated Market Maker): 주문장 없이 수학적 가격 함수로 스왑을 산출하는 엔진
- LP(Liquidity Provider): Liquidity Pool에 자산을 예치하고 LP 지분(share)에 따른 경제적 권리를 획득하는 참여자
- Fee: 스왑 또는 유동성 연산에서 발생하는 비용 항목(프로토콜 정의)
- Revenue Source: 수익의 발생 원천을 식별하는 분류(예: swap_fee, mint_fee 등). 단, 구체 분류 체계는 후속 절에서 확정한다. ([REFERENCE_REQUIRED])

### 2605.3 State/Flow
- 용어는 객체 필드명/이벤트명/감사 레코드의 `action_type` 및 `revenue_source`에 직접 반영된다.

### 2605.4 Validation
- `revenue_source`는 미정의 값 사용을 금지하며, 레지스트리 기반 검증을 요구한다. (레지스트리는 [REFERENCE_REQUIRED])

### 2605.5 Failure handling
- 미정의 용어/코드 사용 시: `UNREGISTERED_TERM_OR_CODE`로 거부

### 2605.6 Audit
- 용어/코드 레지스트리 식별자:
  - `registry_id`, `registry_hash`

### 2605.7 Invariants
- 용어는 결정론적 인코딩(Deterministic Encoding)으로 직렬화되어야 한다.


## 2606. 결정론적 실행 모델(Deterministic Execution Model) 전제

### 2606.1 Purpose
GLPF의 실행 결과가 모든 검증자 노드에서 동일하도록 결정론적 실행 제약을 명문화한다.

### 2606.2 Architecture or Rule
1. 금지 항목(Non-deterministic sources) 금지:
   - 실시간 외부 호출(HTTP), 로컬 시간 의존, 노드별 랜덤, 비결정적 정렬, 비결정적 부동소수점
2. 허용 항목:
   - 트랜잭션 입력, 블록/원장 합의로 고정된 값, 온체인 저장 상태, 명시적 정렬 규칙, 정수/고정소수점 연산(fixed-point)

### 2606.3 State/Flow
- 가격/수수료/분배 계산은 모두 동일 입력 집합을 사용해야 하며, 입력 집합은 감사 레코드로 재구성 가능해야 한다.

### 2606.4 Validation
- 전이 실행 전 “결정론성 검사(Determinism Check)”를 수행하며, 금지 항목 사용 흔적이 있으면 거부한다.
- 수치 연산의 최소 결정론 파라미터(본 배치의 최소 계약):
  1) 고정소수점 스케일(fixed-point scale)은 명시되어야 한다. (구체 스케일 값/자산별 단위는 [REFERENCE_REQUIRED])
  2) 반올림 규칙(rounding rule)은 단일 규칙으로 고정되어야 하며, 노드별 선택을 금지한다. (규칙 레지스트리는 [REFERENCE_REQUIRED])
  3) 오버플로/언더플로 처리(overflow handling)는 “즉시 중단(abort)”으로 고정한다.
  4) 정렬이 필요한 컬렉션 연산은 정렬 키 및 오름/내림을 명시해야 한다.

### 2606.5 Failure handling
- `NON_DETERMINISTIC_EXECUTION_DETECTED`로 거부 및 중단
- 오버플로/언더플로 발생 시: `ARITHMETIC_ABORT`로 중단

### 2606.6 Audit
- 산출값 재현을 위한 최소 필드:
  - `calc_inputs_hash`, `calc_model_id`, `calc_model_version_id`, `calc_model_version_hash`, `fixed_point_scale_id`, `fixed_point_scale_hash`, `rounding_rule_id`, `rounding_rule_hash`

### 2606.7 Invariants
- Canonical ledger state must remain deterministic(결정론 원장 불변)


## 2607. 감사 기록(Audit Recording)과 상태전이 순서 고정 규칙

### 2607.1 Purpose
경제 활동의 추적성(Traceability) 및 불변 감사(Immutable Audit)를 위해 상태전이 파이프라인의 순서를 고정한다.

### 2607.2 Architecture or Rule
GLPF 상태전이의 표준 파이프라인은 다음 순서를 강제한다(헌법 검증 문구와 1:1 정렬).

1. State Proposal 생성
2. Constitution Validation
3. Business Rule Validation
4. Authorization Validation(EA)
5. Consensus Validation
6. Ledger Commit(상태 반영)
7. Audit Recording(append-only, commit-state-hash binding)

Audit Recording은 커밋된 상태(`post_state_hash`)와 불일치할 수 없다. 원자성(atomicity) 보장 메커니즘은 실행 환경 의존으로 [REFERENCE_REQUIRED]로 분리한다.

### 2607.3 State/Flow
- `Proposed` → `ConstitutionValidated` → `BusinessRuleValidated` → `AuthorizationValidated` → `ConsensusValidated` → `Committed` → `Audited`의 내부 단계 마커를 정의한다.
- 단계 마커는 외부에 노출되는 “최종 상태”가 아니라, 검증 파이프라인의 감사 가능성을 위한 메타 상태이다.

### 2607.4 Validation
- `Committed`가 발생했는데 `Audited`가 생성되지 않는 경우는 허용되지 않는다.
- `Audited` 레코드는 `post_state_hash`와 일치해야 한다.

### 2607.5 Failure handling
- 감사 기록 생성 실패 시: 트랜잭션 전체를 실패 처리해야 하며, 원자성 보장 방식(커밋 전 실패/커밋 후 보정 등)은 실행 환경에 의존하므로 [REFERENCE_REQUIRED]로 둔다.
- 실패 코드: `AUDIT_WRITE_FAILURE`

### 2607.6 Audit
- 감사 레코드는 “수명 초과(Beyond Lifetime)” 보존을 전제로 하며, 삭제/수정 불가(append-only) 저장 모델이어야 한다.

### 2607.7 Invariants
- Audit Beyond Lifetime
- Immutable Audit
- Validation Before Execution / Authorization Before Settlement / Consensus Before Finality


## 2608. 계층 독립성(Independent Layers) 및 업그레이드 원칙

### 2608.1 Purpose
각 계층의 독립적 업그레이드 가능성을 인정하되, 헌법적 불변식의 전 계층 동일 적용을 강제한다.

### 2608.2 Architecture or Rule
- Ownership Layer / Execution Layer / Economic Layer / Governance Layer는 독립적으로 업그레이드될 수 있다.
- 단, 헌법적 불변식(Reserve/Ownership/Determinism/Consensus/Audit/Authorization)은 모든 계층에서 동일하게 유지되어야 한다.

### 2608.3 State/Flow
- GLPF 업그레이드는 `framework_version_id` 및 `framework_version_hash` 증가로 표현되며, 구버전 상태와의 호환을 유지해야 한다(backward compatibility).

### 2608.4 Validation
- 업그레이드 트랜잭션은 다음을 포함해야 한다(해시 기반 고정).
  - `from_framework_version_id`, `from_framework_version_hash`
  - `to_framework_version_id`, `to_framework_version_hash`
  - `migration_plan_id`, `migration_plan_hash`
  - `invariant_checklist_hash`
- 업그레이드 후에도 2604 체크리스트를 동일 강도로 통과해야 한다.

### 2608.5 Failure handling
- `BACKWARD_INCOMPATIBLE_CHANGE` 감지 시 업그레이드 거부

### 2608.6 Audit
- 업그레이드 감사 레코드에 `migration_plan_id`, `migration_plan_hash` 및 전후 상태 해시 기록

### 2608.7 Invariants
- Backward Compatibility
- Deterministic Upgrade
- Long-Term Audit Preservation


## 2609. GLPF 객체 모델 미리보기(Preview) — 본 배치의 최소 계약

### 2609.1 Purpose
후속 절(풀/AMM/수익분배/재무/보험)에서 구체화될 객체 모델의 “최소 인터페이스 계약(Minimum Interface Contract)”을 정의한다.

### 2609.2 Architecture or Rule
본 배치에서 정의하는 최소 객체는 다음과 같다(세부 필드는 후속 절에서 확정).

1. `LiquidityPool` (Object)
   - Purpose: 유동성 보관, 스왑 실행, 수수료 축적, 분배 입력 생성
   - Minimal Fields:
     - `pool_id`
     - `asset_types[]` (FT type identifiers)
     - `reserves[]` (balances; 정수/고정소수점 표현만 허용)
     - `fee_model_id`
     - `pool_state` (enum)
     - `created_at_version_id`, `created_at_version_hash`
     - `last_updated_version_id`, `last_updated_version_hash`
2. `RevenueAccumulator` (Object or Sub-Structure)
   - Purpose: 수익원별 누적 및 분배 전 단계 데이터 보관
   - Minimal Fields:
     - `accumulator_id`
     - `revenue_buckets{source_code -> amount}`
     - `period_index` 또는 `epoch`
3. `SegregatedAccounts` (Logical Accounts)
   - Purpose: Treasury/Insurance/Protocol Revenue/User Assets 분리 회계의 식별 단위
   - Minimal Fields:
     - `treasury_account_id`
     - `insurance_account_id`
     - `protocol_revenue_account_id`
     - `user_asset_account_id` (사용자별)

### 2609.3 State/Flow
- `LiquidityPool.pool_state`는 최소 다음 전이를 허용해야 한다.
  - `INIT` → `ACTIVE` → (`PAUSED`) → (`CLOSED`)
- 전이 승인 조건은 BRV/EA/Consensus/Audit 파이프라인을 동일 적용한다.

### 2609.4 Validation
- `asset_types[]`는 등록된 자산 타입만 허용(레지스트리 [REFERENCE_REQUIRED])
- `fee_model_id`는 등록된 모델만 허용([REFERENCE_REQUIRED])

### 2609.5 Failure handling
- 미등록 자산/모델 참조: `UNREGISTERED_ASSET_OR_MODEL`

### 2609.6 Audit
- 풀 생성/상태변경 이벤트는 `pool_id`, `pool_state_pre`, `pool_state_post`, `reason_code`를 포함해야 한다.

### 2609.7 Invariants
- Treasury/Insurance/Protocol/User 자산 혼합 기록 금지(Segregation)
- GLPF 객체 상태전이는 원금 소유권 NFT를 직접 변경할 수 없다(2604.2 `OWNERSHIP_NO_MUTATION`).


## 2610. 본 배치(2601~2610) 준수 요구사항 요약 및 미해결 참조

### 2610.1 Purpose
구현 및 후속 절 작성 시 본 배치가 강제하는 최소 준수 조건과, 현재 문서에 포함되지 않은 참조 대상을 명시한다.

### 2610.2 Architecture or Rule
- 본 배치는 GLPF의 “헌법 상속 + 실행 순서 + 결정론 + 감사 + 분리회계”를 강제하는 상위 계약이다.
- 후속 절은 본 배치의 불변 조건을 약화시키지 않는 범위에서만 구체화될 수 있다.

### 2610.3 State/Flow
- 후속 절에서 정의될 모든 경제 연산은 2607의 파이프라인을 기본 실행 흐름으로 채택해야 한다.

### 2610.4 Validation
- 릴리스/배포 전 검증 체크:
  - 2604 체크리스트 자동화 테스트(또는 형식 검증) 결과가 제공되어야 한다. (검증 도구/형식은 [REFERENCE_REQUIRED])

### 2610.5 Failure handling
- 체크리스트 미충족 릴리스는 `RELEASE_GATE_REJECTED`로 차단되어야 한다.

### 2610.6 Audit
- 릴리스 아티팩트는 최소 다음을 감사 로그로 남겨야 한다(해시 기반 고정).
  - `release_id`, `build_hash`
  - `framework_version_id`, `framework_version_hash`
  - `constitution_version_id`, `constitution_version_hash`
  - `invariant_checklist_hash`
  - `registry_id`, `registry_hash` (용어/코드/모델 레지스트리)

### 2610.7 Invariants
- New modules must preserve backward-compatible constitutional invariants.

### 2610.8 [REFERENCE_REQUIRED]
- 상세 용어집/코드 체계/레지스트리(용어, `revenue_source`, 실패 코드, 모델 ID)
- Chapter 3O 전체 절 구조 및 후속 절 번호(섹션 인덱스)
- 불변식 레지스트리(invariant registry): invariant_id/키/정의/검증 방법
- BRVF/EAF/GRBF/PDBRF의 인터페이스 및 버전 식별(온체인 레지스트리 고정 포함)
- 고정소수점 스케일/자산 단위/반올림 규칙 레지스트리
- 감사 저장 모델의 원자성(atomicity) 보장 방식(실행 환경 의존)
- 토큰 발행/소각(issuance/mint/burn) 범위 및 검증 프레임워크(본 배치에서는 비범위)
```

<-bash: cd: /home/boshin57/tobmate-agent-factory: No such file or SOURCE: workspace/drafts/3O_2611_2620_approved.md -->
## 2611. Liquidity Pool Object 정의: 식별자, 자산쌍, 준비금 참조, 수수료 파라미터

### Purpose
GLPF의 모든 유동성(Liquidity) 상태를 **결정적(deterministic)** 으로 표현하는 표준 Pool 객체를 정의하고, Pool이 다루는 자산쌍(Asset Pair), 준비금 참조(Reserve Reference), 수수료/리스크 파라미터(Fee/Risk Parameters)를 **불변식과 검증 규칙**으로 고정한다.

### Architecture or Rule
1. Pool은 **Shared Object** 로서 전역 상태를 갖고, 각 사용자의 권리는 별도 **Position Object(LP Position)** 로 표현한다.
2. Pool은 다음을 직접 보유하거나 참조한다.
   - FT 준비금(reserve balances): on-chain vault balance(분리 Vault)
   - NFT 인벤토리(inventory): Hybrid/NFT Pool에서만 선택적으로 보유(단, 소유권 이전이 아닌 위임/잠금 모델에 한정; 2612 참조)
   - 준비금/원금 소유권/감사에 대한 **참조 무결성용 Reference**(ReserveRef/OwnershipDomainRef/AuditRef)
3. Pool은 **원금 소유권(Principal Ownership)** 을 생성/변경/소각하지 않으며, Pool 참여는 **경제적 이용권(Economic Utilization)** 범위에서만 발생한다. (Constitution 2, 3)
4. GLPF Ref(ReserveRef/OwnershipDomainRef/AuditRef/OracleRef)의 공통 불변 규칙은 2616에 따른다(타겟 불변, 버전 규칙, 폐기 금지, 권한 통제).

### State/Flow
- `Pool.status` 상태 예시(구현 시 enum 권장)
  - `PENDING_ACTIVATION` → `ACTIVE` → (`PAUSED` | `FROZEN`) → `CLOSED`
- 생성(Create Pool) 흐름(요약)
  1. 파라미터 정합성 검증(자산쌍, fee, tick/curve type 등)
  2. Segregation 라우팅 검증(사용자/트레저리/보험/프로토콜 금고 분리)
  3. 참조(ReserveRef/OwnershipDomainRef/AuditRef, 필요 시 OracleRef) 바인딩
  4. `PoolCreated` 이벤트 및 Audit record 생성(결정적 시간원/비결정 메타데이터 구분은 2611.Audit 및 2619/2614 참조)

### Validation
- Business Rule Validation(Chapter 3N 기반)
  - `asset_a != asset_b`
  - `fee_bps` 범위, `protocol_fee_bps` 범위, `max_slippage_bps` 범위
  - `curve_type`(AMM invariant 타입)과 `oracle_guard_policy_id` 호환성
  - Hybrid Pool인 경우 `nft_policy_id` 및 `valuation_policy_id` 필수
  - `segregation_policy_id`가 Treasury/Insurance/User vault 경로를 혼합하지 않음
  - 참조 ID들이 존재하며([REFERENCE_REQUIRED] object_registry.md), 2616의 Ref 공통 불변 규칙 및 버전 규칙(`version`, `policy_version`)을 만족
- Execution Authorization(Chapter 3N 기반)
  - Pool 생성/상태 변경은 `Liquidity Authorization` + 필요 시 `DAO Authorization`(규제형/기관형 Pool)
  - `FROZEN/UNFROZEN` 전이는 `Emergency Authorization` 필요

### Failure handling
- `E1002 Unauthorized Caller`: 생성/수정 권한 없음
- `E1007 Business Rule Violation`: fee/curve/policy/ref 규칙 불일치, oracle TTL 위반 등
- `E1008 Invalid Object State`: ACTIVE 아닌데 유동성 조작 시도 등
- `E1006 Policy Version Mismatch`: 정책 버전 불일치
- 실패 시: 상태 변경/자산 이동/이벤트 발행은 **원자적 롤백(atomic rollback)**

### Audit
- 이벤트(필수)
  - `PoolCreated { pool_id, asset_a, asset_b, curve_type, fee_bps, created_by, time_ref, meta_ts? }`
  - `PoolStatusChanged { pool_id, from, to, authorized_by, time_ref, meta_ts? }`
  - `PoolParamsUpdated { pool_id, fields_changed_hash, authorized_by, time_ref, meta_ts? }`
- Audit Object 기록(필수)
  - `audit_ref`에 `state_hash`, `policy_hash`, `auth_context_hash`를 append-only로 저장
- 시간/타임스탬프 규칙
  - `time_ref`는 합의적으로 재현 가능한 값(예: tx_digest, checkpoint_sequence, checkpoint_timestamp_ms)을 사용한다.
  - `meta_ts?`(선택)는 비결정적 메타데이터일 수 있으며, **canonical state hash 산출 입력에 포함하지 않는다**. (Constitution 6)

### Invariants
1. Pool은 **원금 NFT(Principal Ownership NFT)** 의 소유권 상태를 직접 변경하지 않는다. (Constitution 2, 3)
2. Pool 상태 전이는 BRV + EA를 모두 통과해야 한다. (Constitution 4)
3. Pool의 수수료 분배 및 회계는 Segregation을 위반하지 않는다. (Constitution 8)
4. 동일 입력에서 동일 출력의 결정성 보장(oracle 라운드 고정 입력 포함, 비결정적 메타데이터 배제). (Constitution 6)


---

## 2612. Principal Ownership NFT와 경제적 이용권 FT 분리의 GLPF 적용 규칙

### Purpose
GLPF에서 “원금 소유권(Ownership Right)”과 “경제적 이용(Economic Utilization Right)”을 혼합하여 **중복 상환권, 묵시적 희석, 소유권 오인**이 발생하지 않도록, Pool 단위에서 적용되는 분리 규칙을 명시한다.

### Architecture or Rule
1. Pool은 다음 중 하나의 권리만을 직접 취급한다.
   - FT 기반 Pool: FT↔FT 유동성 및 가격 발견
   - NFT 기반/Hybrid Pool: NFT는 **평가·인벤토리·거래대기** 목적의 경제적 사용에 한정되며, 원금 소유권 이전은 별도의 NFT 전이 규칙(Chapter 3N)에 따름
2. NFT 예치(Deposit)는 “소유권의 풀 귀속(escrow transfer)”이 아니라, **소유권 유지 + 경제적 사용 권한 위임(Delegated Utilization)** 으로만 모델링한다.
   - (a) **Principal Ownership NFT의 owner는 예치 전후 불변**이다.
   - (b) Pool이 필요로 하는 통제는 소유권 이전이 아니라 **Lock 플래그(잠금 상태)** 및 **철회 가능(revocable) 위임 권한 객체**로만 표현한다.
   - (c) 위임은 범위(scope)·만료(expiry)·철회(revocation)를 포함하며, 만료/철회 시 Pool은 더 이상 NFT를 사용(매칭/체결/인출 제한)할 수 없다.
3. 금지 규칙(명시)
   - Pool 참여 또는 위임만으로 특정 Physical Gold 인도권 자동 부여 금지
   - “NFT 예치 → FT 발행/상환”의 직접 루프 금지(중복 상환권 방지)

### State/Flow
- UtilizationDelegation 기반 NFT 단독 예치(Single-Sided Gold NFT Deposit) 흐름(요약)
  1. 사용자: `deposit_nft_for_utilization(pool_id, nft_id, scope, expiry_ms, auth_context)` 호출
  2. BRV: NFT 도메인/상태/정책 적합성, scope 허용성, expiry 범위 검증
  3. EA: `NFT Authorization` + `Ownership Authorization`(소유자 확인) + 정책에 따른 `Liquidity Authorization`
  4. **Lock 설정(비소유권 이전)**
     - NFT에 직접 상태를 추가할 수 없는 경우, `NFTLockRecord{ nft_id, locker_domain=pool_id, lock_until, revocable=true }` 형태의 별도 레코드 객체로 표현([REFERENCE_REQUIRED])
  5. `UtilizationDelegation` 객체 생성(예: Owned 또는 Shared+권한 기반; 구현 선택)
     - `UtilizationDelegation { id, nft_id, owner_tmid_id?, pool_id, scope, expiry_ms, revocation_nonce, status }`
  6. `valuation_policy_id`로 Principal/Premium 분리 평가(결정적 입력 고정)
  7. `protocol_liquidity_matching_policy_id`에 따라 반대편 FT 매칭(프로토콜 또는 제3자)
  8. LP Position 발급(단, Position은 Pool share이며 원금 소유권과 무관)
- 위임 해지/만료 처리
  - 사용자 또는 정책 주체(허용된 경우): `revoke_delegation(delegation_id, reason, auth_context)`
  - 만료(expiry_ms) 도래 후 사용 시도는 BRV에서 거부하며, 필요 시 “정리(clean-up)” 트랜잭션으로 Lock 해제 및 delegation 종료 처리
- FT 단독/양면 예치: Pool의 FT Vault만 변경, Principal Ownership NFT와 무관

### Validation
- NFT가 포함되는 모든 흐름은 다음을 만족해야 한다.
  - NFT의 소유자 불변(owner 유지) 및 `Ownership Authorization` 검증
  - Lock/Delegation이 존재하고 유효(expiry 미경과, 미철회)하며 scope가 요청 액션과 일치
  - `valuation_policy_id`에 따른 Principal/Premium 분리 및 `premium_haircut_bps` 등 리스크 조정 규칙 적용
  - “위임 생성/갱신/철회”는 명시적 엔트리로만 수행되며, swap/add/remove 내부에서 암묵 갱신 금지
- 권한
  - 위임 생성/철회: `NFT Authorization` + `Ownership Authorization` 필수
  - FT 이동: `Financial Authorization`
  - Hybrid 매칭 정책 실행: `Liquidity Authorization` + 정책에 따라 `Treasury/DAO Authorization` 추가

### Failure handling
- 평가 실패/정책 불일치 시: Lock/Delegation/Pool 상태 변경은 **모두 원자 롤백**, NFT 소유권은 변하지 않는다.
- 만료/철회된 delegation 사용 시도: `E1007 Business Rule Violation`
- 중복 권리 가능성 감지 시: `E1007 Business Rule Violation`

### Audit
- `NFTUtilizationDelegated { pool_id, nft_id, delegation_id, scope, expiry_ms, owner, time_ref, meta_ts? }`
- `NFTLockSet { nft_id, lock_domain=pool_id, lock_until, delegation_id, time_ref, meta_ts? }`
- `DelegationRevoked { delegation_id, reason_code, authorized_by, time_ref, meta_ts? }`
- 모든 NFT 관련 전이는 `audit_ref`에 원인 트랜잭션 및 `auth_context_hash` 저장

### Invariants
1. 동일 실물 금에 대해 NFT와 FT에 **동일한 무조건부 상환권**을 동시에 부여하지 않는다. (Constitution 3, 9)
2. Pool 참여는 원금 소유권을 묵시적으로 변경하지 않는다(소유자 불변 + 위임/잠금만 허용). (Constitution 2, 3)


---

## 2613. Pool Share 표현: LP 포지션(예: LP-NFT 또는 Position Object) 설계 원칙

### Purpose
Pool 지분, 수익 분배 권리, 잠금/규제 제한을 **개별 포지션 단위**로 표현하여, 전송 제한(Transfer Restriction), 수익 인덱싱(Fee Index), 감사 추적을 구현한다.

### Architecture or Rule
1. LP 권리는 FT(균질 토큰) 대신 **Position Object(NFT형 포지션)** 를 표준으로 한다.
2. Position은 다음을 표현한다.
   - 지분 단위(`liquidity_units` 또는 `lp_units`)
   - 원금/프리미엄 분리 지분(하이브리드에서 `principal_share`, `premium_share`)
   - 수익 인덱스 체크포인트(`accumulated_fee_index` 또는 fee_growth_checkpoint)
   - 잠금/규제(`lock_until`, `risk_tier`, `transfer_policy_id`)
3. 규제/비규제 모드 소유자 우선 규칙
   - `owner_tmid_id`가 설정된 Position은 규제형(regulated)으로 간주하며, **소유/이전/청구 권한의 기준은 TMID** 이다.
   - 규제형 Position의 `owner: address`는 수탁/표시 목적의 보조 필드일 수 있으나, **권한 판단에 사용하지 않는다**.
   - `transfer_policy_id`가 설정된 Position은 해당 정책이 허용하는 경우에만 제3자 이전이 가능하며, 정책 미설정 시 기본은 이전 제한(deny-by-default)으로 한다([REFERENCE_REQUIRED]).

### State/Flow
- `Position.status` 예시
  - `CREATED` → `ACTIVE` → (`LOCKED` | `EXIT_PENDING`) → (`CLOSED`)
- Liquidity Add/Remove는 Position 단위로 수행하며, Pool과 Position의 업데이트는 단일 트랜잭션에서 원자적으로 수행

### Validation
- Add
  - Pool ACTIVE
  - 입력 자산 타입 일치
  - 슬리피지/데드라인 만족
  - LP units 계산 결정성 보장(정수 연산 규격 고정)
- Remove
  - Position 소유자(TMID 또는 address) 및 전송 제한 검증
  - 잠금 기간/리스크 정책 검증
  - 미청구 수수료 정산 후 원금 반환

### Failure handling
- 잠금/이전 제한 위반: `E1004 Permission Denied`
- 비율/슬리피지 위반: `E1007 Business Rule Violation`
- 상태 불일치: `E1008 Invalid Object State`

### Audit
- `PositionMinted { position_id, pool_id, owner_tmid_id?, owner?, lp_units, time_ref, meta_ts? }`
- `LiquidityAdded { position_id, amount_a, amount_b, minted_lp_units, time_ref, meta_ts? }`
- `LiquidityRemoved { position_id, burned_lp_units, out_a, out_b, time_ref, meta_ts? }`

### Invariants
1. Position은 원금 NFT 소유권 자체가 아니라 **Pool Share**만을 나타낸다.
2. Position 단위의 수익 누적은 인덱스 기반으로 재현 가능해야 한다(결정성). (Constitution 6)


---

## 2614. 가격 오라클/내부 가격 함수 경계(AMM invariant와 분리)

### Purpose
AMM의 가격 함수(invariant)와 외부 가격 참조(Oracle)를 혼동하여 **비결정성, 조작 가능성, 정책 우회**가 발생하지 않도록 경계를 정의한다.

### Architecture or Rule
1. AMM Engine은 `curve_type`에 의해 정의된 **순수 함수적 상태 전이**만 수행한다.
2. Oracle은 “가격 결정”이 아니라 **가드(guard)** 로만 사용한다.
   - 예: `max_deviation_bps`, `min_liquidity`, `circuit_breaker_threshold`
3. Oracle 입력 결정성 규칙
   - (a) `oracle_round`(또는 `oracle_record_id`)는 **트랜잭션 파라미터로 명시**되어야 한다.
   - (b) `oracle_ref`가 가리키는 라운드 레코드는 **append-only/immutable** 이어야 하며, 동일 라운드 값은 변경되지 않는다.
   - (c) 오라클 업데이트(새 라운드 추가)는 GLPF 외부의 전용 경로로 제한되며, 최소한 `Validator Authorization` 또는 `DAO Authorization` 또는 [REFERENCE_REQUIRED] `Oracle Authorization`을 요구한다.
4. 오류 코드 정정
   - 오라클 미제공/TTL 만료/편차 초과 등 “가드 정책 위반”은 `E1007 Business Rule Violation`로 처리한다.
   - `E1009 Authorization Expired`는 `auth_context` 만료에만 사용한다.

### State/Flow
- Swap/Join/Exit 실행 전:
  1. AMM 산출 가격/슬리피지 계산
  2. Oracle guard 검증(편차/급변/정지 조건, TTL)
  3. 통과 시에만 실행(불통과 시 상태 변화 없음)

### Validation
- `oracle_guard_policy_id` 존재 및 버전 일치
- oracle 라운드 레코드의 TTL(정책 기반) 미경과
- 편차 초과 시 거래 거부 또는 `PAUSED` 전환(정책 선택; `PAUSED` 전환은 별도 EA 필요)

### Failure handling
- oracle 미제공/만료/TTL 초과: `E1007 Business Rule Violation`
- 편차 초과: `E1007 Business Rule Violation`
- 정지 상태에서 swap 시도: `E1008 Invalid Object State`

### Audit
- `OracleGuardChecked { pool_id, oracle_round, price, deviation_bps, result, time_ref, meta_ts? }`
- `CircuitBreakerTriggered { pool_id, reason_code, oracle_round, time_ref, meta_ts? }`

### Invariants
1. Oracle은 AMM의 invariant를 대체하지 않으며, 실행 허용 여부만 결정한다.
2. Oracle 소비는 라운드 고정 + immutable 레코드 전제로 결정성을 보장한다. (Constitution 6)


---

## 2615. Treasury/Insurance/사용자 자산의 분리 보관(Segregation) 매핑

### Purpose
GLPF에서 발생하는 모든 자산 흐름이 “Treasury, Insurance Reserve, Protocol Revenue, User Assets”의 **계정/객체 분리**를 위반하지 않도록, Pool 단위의 보관 구조와 라우팅 규칙을 정의한다. (Constitution 8)

### Architecture or Rule
1. Pool은 자산을 다음 Vault로 **분리 보관**한다(개념적으로 분리된 Balance이며, 접근 권한은 capability로 강제).
   - `user_liquidity_vault`: LP가 제공한 유동성 원본(사용자 자산)
   - `protocol_fee_vault`: 프로토콜 수수료(Protocol fee; 프로토콜 수익)
   - `route_treasury_vault`: Treasury 귀속 예정분(정책에 의해 적립; 미이관 상태)
   - `route_insurance_vault`: Insurance 귀속 예정분(정책/리스크 이벤트에 의해 적립; 미이관 상태)
2. Vault 소유/출금 capability 경계(강제 규칙)
   - Pool 엔트리 함수가 직접 변경할 수 있는 범위
     - `user_liquidity_vault`: swap/add/remove/claim에 의해 변경 가능
     - `protocol_fee_vault`: swap에 의해 적립 가능(출금 불가)
     - `route_*_vault`: **적립(credit)만 가능**, Treasury/Insurance로의 최종 이관(debit)은 불가
   - 최종 이관 권한
     - `route_treasury_vault → Treasury` 이관은 **Treasury 모듈**만 수행하며 `Treasury Authorization`을 요구
     - `route_insurance_vault → Insurance` 이관은 **Insurance 모듈**만 수행하며 정책에 따른 `Emergency/DAO Authorization`을 추가로 요구할 수 있음
3. 수수료/수익 분배는 “Pool 내부 누적(적립) → 정책에 따른 라우팅(적립) → 별도 모듈 이관(출금)”의 3단계로 수행한다.
4. 위 규칙을 우회하는 direct transfer(예: Pool이 Treasury 객체에 직접 전송)는 BRV에서 금지한다.

### State/Flow
- Swap 발생
  1. `user_liquidity_vault` 변화
  2. `protocol_fee_vault` 적립(프로토콜 수익)
  3. epoch/트리거 시 MRDF 정책에 따라 `route_treasury_vault`, `route_insurance_vault`로 **적립**(Pool 또는 MRDF가 수행; 단, Treasury/Insurance “이관”은 수행 불가)
- Treasury/Insurance 이관(별도 흐름)
  1. `settle_route_to_treasury(pool_id, amount, auth_context)` (Treasury 모듈)
  2. `settle_route_to_insurance(pool_id, amount, auth_context)` (Insurance 모듈)
- LP Claim
  - LP 몫은 인덱스 계산으로 `user_liquidity_vault`에서 지급(프로토콜/보험/트레저리 Vault와 혼합 금지)

### Validation
- Vault 간 이체는 항상 목적지/출처가 분리 규칙을 만족해야 함(허용된 edge만 통과)
- Treasury/Insurance로의 “이관(debit)”은 해당 모듈 엔트리 + 해당 권한을 요구
- 라우팅 정책(`segregation_policy_id`) 버전 고정 및 BRV에서 검증

### Failure handling
- 잘못된 Vault 라우팅 또는 금지된 direct transfer 시도: `E1007 Business Rule Violation`
- 권한 부족: `E1002 Unauthorized Caller`

### Audit
- `FeeAccrued { pool_id, fee_a, fee_b, protocol_fee_a, protocol_fee_b, time_ref, meta_ts? }`
- `SegregationRouted { pool_id, to_route_treasury, to_route_insurance, policy_id, time_ref, meta_ts? }`
- `RouteSettledToTreasury { pool_id, amount, authorized_by, time_ref, meta_ts? }`
- `RouteSettledToInsurance { pool_id, amount, authorized_by, time_ref, meta_ts? }`

### Invariants
1. 사용자 유동성과 프로토콜 수익/보험/트레저리 자산은 동일 Vault에 공존하지 않는다. (Constitution 8)
2. 어떠한 유동성 연산도 Segregation을 우회할 수 없다(credit-only route + 이관 전용 권한). (Constitution 5, 8)


---

## 2616. 객체 간 참조 무결성(ReserveRef, OwnershipDomainRef, AuditRef, OracleRef) 및 Ref 공통 불변 규칙

### Purpose
Liquidity Pool 및 Position이 Reserve/Ownership/Audit/Oracle 계층과 연결될 때, 참조가 끊기거나 위조되어 **준비금 우회, 소유권 혼선, 감사 단절, 오라클 조작**이 발생하지 않도록 참조 객체 모델과 검증 규칙을 정의한다.

### Architecture or Rule
1. 표준 참조 객체(예시; 실제 타입/레지스트리는 [REFERENCE_REQUIRED] object_registry.md에 따라 확정)
   - `ReserveRef`: 특정 Reserve Object 또는 Reserve Registry에 대한 참조(읽기/검증용)
   - `OwnershipDomainRef`: NFT/소유권 검증이 속한 도메인/정책 레지스트리 참조(검증 라우팅용)
   - `AuditRef`: append-only audit trail sink
   - `OracleRef`: 오라클 라운드 레코드 집합에 대한 참조(가드용)
2. Ref 공통 불변 규칙(본 섹션에서 GLPF 범위로 고정)
   - (a) `target_id` 불변: Ref 생성 이후 `target_id`는 변경 불가
   - (b) `domain` 불변: Ref 생성 이후 `domain`은 변경 불가
   - (c) `version` 규칙: Ref 자체의 `version`은 단조 증가만 허용(감소/리셋 금지)
   - (d) 폐기/회수 금지: Ref는 burn/revoke로 “검증 우회”를 만들 수 없으며, 비활성화가 필요하면 `status`를 append-only 로그로 남기고, BRV에서 “비활성 Ref 사용 금지”로 처리한다([REFERENCE_REQUIRED])
   - (e) 생성/갱신 권한: Ref 생성/갱신은 해당 도메인에 상응하는 EA 카테고리를 요구한다
     - `ReserveRef`: `Reserve Authorization`
     - `OwnershipDomainRef`: `Ownership Authorization` 또는 `DAO Authorization`(정책에 따름)
     - `AuditRef`: 프로토콜 배포/거버넌스 경로에 한정([REFERENCE_REQUIRED])
     - `OracleRef`: `Validator Authorization` 또는 `DAO Authorization` 또는 [REFERENCE_REQUIRED] `Oracle Authorization`
   - (f) Ref 검증 실패 시: **모든 경제 전이(스왑/예치/인출/청구/라우팅)를 거부**한다. (Constitution 4, 5)
3. 참조는 “주소 문자열”이 아니라 **온체인 ID**로만 연결하며, 각 참조는 `version`과 `domain`을 포함한다.

### State/Flow
- Pool 생성 시 `reserve_ref_id`, `audit_ref_id`는 필수
- Hybrid Pool 또는 NFT 연계 Pool은 `ownership_domain_ref_id` 또는 `nft_policy_id`에 의해 Ownership 검증 경로가 활성화
- Oracle guard가 활성인 Pool은 `oracle_ref_id`를 포함하고, 각 실행에서 `oracle_round`를 지정하여 소비
- 모든 핵심 전이(Create/ParamUpdate/Pause/Swap/Add/Remove/Claim/Route)에서 `audit_ref`에 기록

### Validation
- 참조 존재성: ID가 가리키는 객체가 실재
- 도메인 일치: Pool이 취급하는 자산 도메인과 ref 도메인 일치
- 버전/정책 일치: `policy_version` mismatch 금지 및 Ref `version` 규칙 준수
- 준비금 우회 방지(간접 검증): `ReserveRef`가 가리키는 타겟이 “검증된 준비금 선존재” 상태임을 확인하는 검증 훅이 존재해야 하며, 미충족 시 전이 거부([REFERENCE_REQUIRED] 구체 훅 정의)

### Failure handling
- ref 미존재/비활성/검증 실패: `E1007 Business Rule Violation` 또는 `E1008 Invalid Object State`(전이 단계에 따라)
- ref 도메인 불일치/버전 불일치: `E1006 Policy Version Mismatch` 또는 `E1007 Business Rule Violation`

### Audit
- `ReferenceBound { pool_id, reserve_ref_id, audit_ref_id, ownership_domain_ref_id?, oracle_ref_id?, time_ref, meta_ts? }`
- `ReferenceCheckFailed { pool_id, ref_type, ref_id, reason_code, time_ref, meta_ts? }`

### Invariants
1. Reserve/Ownership/Audit/Oracle 참조는 상태 전이마다 검증되어야 하며, 누락/실패 시 실행 불가. (Constitution 4)
2. AuditRef는 모든 경제 전이에 대해 append-only로 유지되어야 한다. (Constitution 7, 9)


---

## 2617. 핵심 객체 스키마(Object Schema) — Pool/Position/Ref 최소 필드

### Purpose
GLPF 구현에 필요한 최소 객체 필드 집합을 명시하여, Move 모듈 설계 시 타입/필드 누락으로 인한 비호환과 불변식 훼손을 방지한다.

### Architecture or Rule
아래 스키마는 “최소 요건”이며, 세부 타입/레지스트리 연결은 [REFERENCE_REQUIRED] object_registry.md에서 확정한다.

#### 1) LiquidityPool (Shared Object)
- `id: UID`
- `pool_type: u8` (FT_ONLY / NFT_ONLY / HYBRID)
- `asset_a_type: TypeTag`
- `asset_b_type: TypeTag`
- `curve_type: u8` (constant_product / stable_swap / concentrated 등)
- `status: u8`
- `fee_bps: u32`
- `protocol_fee_bps: u32`
- `max_slippage_bps: u32`
- `oracle_guard_policy_id: ID`
- `segregation_policy_id: ID`
- `valuation_policy_id: Option<ID>` (NFT/HYBRID)
- `nft_policy_id: Option<ID>` (NFT/HYBRID)
- `protocol_liquidity_matching_policy_id: Option<ID>` (NFT/HYBRID)
- `transfer_policy_id: Option<ID>` (규제형/제한형)
- `reserve_ref_id: ID`
- `ownership_domain_ref_id: Option<ID>` (NFT/HYBRID)
- `oracle_ref_id: Option<ID>` (oracle guard 사용 시)
- `audit_ref_id: ID`
- `total_lp_units: u128`
- `vault_user_a: Balance<A>` / `vault_user_b: Balance<B>` (개념 필드)
- `vault_protocol_fee_a: Balance<A>` / `vault_protocol_fee_b: Balance<B>`
- `vault_route_treasury_a: Balance<A>` / `vault_route_treasury_b: Balance<B>` (개념 필드)
- `vault_route_insurance_a: Balance<A>` / `vault_route_insurance_b: Balance<B>` (개념 필드)
- `global_fee_index_a: u256` / `global_fee_index_b: u256` (결정적 회계용)
- `created_at_ms: u64` (결정적 시간원에 의해 산출; 2611.Audit 규칙)
- `updated_at_ms: u64`
- `param_version: u64`

#### 2) LPPosition (Owned Object)
- `id: UID`
- `pool_id: ID`
- `owner: address` (비규제 모드 기본)
- `owner_tmid_id: Option<ID>` (규제 모드에서 설정; 설정 시 권한 판단 기준)
- `lp_units: u128`
- `principal_share: u128` (HYBRID 선택)
- `premium_share: u128` (HYBRID 선택)
- `fee_growth_checkpoint_a: u256`
- `fee_growth_checkpoint_b: u256`
- `unclaimed_fee_a: u128`
- `unclaimed_fee_b: u128`
- `lock_until: u64`
- `risk_tier: u8`
- `transfer_policy_id: Option<ID>`
- `status: u8`
- `created_at_ms: u64`
- `updated_at_ms: u64`
- `generation: u64`

#### 3) Reference (ReserveRef/OwnershipDomainRef/AuditRef/OracleRef) 공통 최소 필드
- `id: UID`
- `ref_type: u8`
- `domain: u64`
- `target_id: ID`
- `version: u64`
- `status: u8` (활성/비활성 등; 폐기 대신 상태로 표현)
- `created_at_ms: u64`
- `updated_at_ms: u64`

#### 4) UtilizationDelegation (NFT 경제적 사용 권한 위임; 2612)
- `id: UID`
- `nft_id: ID`
- `pool_id: ID`
- `owner_tmid_id: Option<ID>`
- `scope: u64` (bitmask 권장; [REFERENCE_REQUIRED])
- `expiry_ms: u64`
- `revocation_nonce: u64`
- `status: u8` (ACTIVE/REVOKED/EXPIRED)
- `created_at_ms: u64`
- `updated_at_ms: u64`

### Validation
- Pool/Position/Delegation/Ref 생성 시: 필수 필드 누락 금지, `param_version` 및 `version` 단조 증가 규칙 고정
- 타입 태그(TypeTag) 기반 자산쌍 검증은 런타임 결정성을 해치지 않는 방식으로 고정

### Failure handling
- 필수 필드/타입/규칙 불일치: `E1007 Business Rule Violation`

### Audit
- `SchemaVersionStamped { object_id, schema_version, time_ref, meta_ts? }` (선택)

### Invariants
- `total_lp_units`는 모든 ACTIVE Position의 `lp_units` 합과 일관되어야 한다(동일 트랜잭션 내 갱신). (Constitution 6)


---

## 2618. Pool 생성/업데이트 권한 모델(Authorization Surface) — GLPF 범위 확정

### Purpose
Pool/Position/참조 바인딩에 필요한 Authorization Category를 GLPF 관점에서 확정하고, 권한 누락에 의한 정책 우회(예: 무단 수수료 변경, 임의 Freeze 해제)를 방지한다.

### Architecture or Rule
1. Authorization Category 매핑(Chapter 3N Table 1 기반 적용)
   1) Pool 생성/파라미터 변경: `Liquidity Authorization` (+ 규제형은 `Regulatory Authorization`, 필요 시 `DAO Authorization`)
   2) Pool 상태(PAUSED/FROZEN) 변경:
      - PAUSE: `Liquidity Authorization` 또는 정책상 `DAO Authorization`
      - FREEZE/UNFREEZE: `Emergency Authorization`
   3) Treasury/Insurance 라우팅 “이관”: 각각 `Treasury Authorization`, `Emergency/DAO Authorization`(정책)
   4) NFT 위임/잠금/해지: `NFT Authorization` + `Ownership Authorization`
   5) 사용자 입출금/스왑: `Identity Authorization` + `Financial Authorization`
2. BRV→EA→Execute 순서 강제
   - 모든 엔트리 함수(entry function)는 `auth_context`를 입력으로 받고,
     1) BRV 통과  
     2) EA 통과  
     3) 상태 전이 실행  
     순서를 강제한다. (Constitution 4)

### State/Flow
- `auth_context` 최소 스키마(GLPF 고정)
  - `auth_id: ID` (또는 digest)
  - `issuer: address` 또는 `issuer_object_id: ID`(권한 발급 주체)
  - `category_mask: u64` (Authorization Category bitmask)
  - `nonce: u64`
  - `expiry_ms: u64`
  - `scope_object_ids_hash: vector<u8>` (대상 객체 ID 집합의 커밋)
  - `policy_version: u64`
- 감사 해시 규격(최소 고정)
  - `auth_context_hash = H(auth_id || issuer || category_mask || nonce || expiry_ms || scope_object_ids_hash || policy_version)`
  - `auth_context_hash`는 `audit_ref`에 기록되어야 한다.

### Validation
- `auth_context.expiry_ms` 만료 시 거부(`E1009`)
- `nonce` 재사용 탐지 시 거부(`E1010`)
- `scope_object_ids_hash`가 실제 입력 객체 집합과 불일치 시 거부(`E1007`)

### Failure handling
- `E1009 Authorization Expired`
- `E1010 Replay Attack Detected`

### Audit
- `AuthorizationChecked { action, pool_id?, position_id?, auth_id, category_mask, result, time_ref, meta_ts? }`

### Invariants
- BRV/EA를 통과하지 못한 상태 전이는 절대 커밋되지 않는다. (Constitution 4)


---

## 2619. 결정적 회계(Deterministic Accounting)와 Pool 단위 상태 해시

### Purpose
LP 수익, 프로토콜 수수료, 라우팅 잔고가 입력에 대해 재현 가능한 방식으로 계산되어, 합의(Consensus) 및 감사(Audit)에서 동일 결과를 보장한다. (Constitution 6, 7)

### Architecture or Rule
1. 모든 누적 변수는 정수 기반 고정소수(fixed-point) 규격을 사용한다.
2. Pool은 선택적으로 `state_hash`(또는 `state_commitment`)를 유지하여, 핵심 필드 집합에 대한 커밋을 감사에 제공한다.
3. fee growth 모델은 “글로벌 인덱스 + 포지션 체크포인트”를 기본으로 한다.
4. `state_hash` 산출 입력에는 비결정적 메타데이터(예: `meta_ts?`)를 포함하지 않는다.

### State/Flow
- Swap마다:
  - `global_fee_index_a/b` 증가
  - 프로토콜 fee 분리 적립
- Claim:
  - `owed = (global_index - checkpoint) * lp_units` 형태로 결정적 계산
  - 지급 후 checkpoint 갱신

### Validation
- 오버플로/언더플로/div-by-zero 방지(명시적 체크)
- 인덱스 증가량은 swap 입력/fee 파라미터에서 단일 방식으로 도출

### Failure handling
- 산술 예외(overflow/underflow/div-by-zero 포함)는 GLPF 범위에서 **`E1007 Business Rule Violation`로 통일**한다.
- 실패 시 원자적 롤백(atomic rollback)

### Audit
- `FeeIndexUpdated { pool_id, delta_a, delta_b, new_index_a, new_index_b, time_ref, meta_ts? }`
- `StateCommitted { pool_id, state_hash, time_ref, meta_ts? }`

### Invariants
- 동일 트랜잭션 집합에 대해 `global_fee_index` 및 `state_hash`는 노드 간 동일해야 한다. (Constitution 6)


---

## 2620. GLPF 객체 경계 요약 및 하위 모듈 입력 계약(Interface Contract)

### Purpose
2611~2619에서 정의한 객체 모델을 AMM Engine, Fee Distribution, Treasury/Insurance, DAO Governance가 **침범하지 않는 경계**로 고정하여, 이후 모듈 추가 시 헌법 불변식의 하위 호환성을 보장한다. (Constitution 10)

### Architecture or Rule
1. AMM Engine
   - 입력: `LiquidityPool`, swap/add/remove 파라미터, (고정된) `oracle_round`(선택)
   - 출력: Pool `user_liquidity_vault` 변화량, fee 산출
   - 금지: Treasury/Insurance “이관”, Ownership NFT owner 변경, Delegation 암묵 갱신, AuditRef 임의 변조
2. Fee Distribution(MRDF)
   - 입력: `protocol_fee_vault`, `segregation_policy_id`, epoch 트리거
   - 출력: `route_*_vault`로의 적립(credit)
   - 금지: `route_*_vault`의 Treasury/Insurance 최종 이관(debit)
3. Treasury/Insurance
   - 입력: `route_*_vault` 잔고, 승인 컨텍스트
   - 출력: 목적 계정/객체로 이관(debit), 감사기록
4. DAO Governance
   - 입력: 정책 업데이트 제안, 파라미터 변경 요청
   - 출력: 승인/거부 및 버전 증가

### Validation
- 각 모듈은 공통적으로 BRV→EA→Execute 순서를 준수
- 모듈 간 호출은 반드시 `policy_id/version` 및 `auth_context`를 명시하여 결정성 및 감사 가능성을 확보

### Failure handling
- 경계 침범 감지 시 즉시 실패 처리(`E1007`)

### Audit
- 모듈별 실행 로그는 모두 `audit_ref_id`로 수렴(append-only)

### Invariants
1. Liquidity 연산은 Reserve/Ownership/Consensus/Audit 불변식을 우회할 수 없다. (Constitution 5)
2. 새 모듈은 본 객체 경계 및 참조 무결성을 유지해야 한다. (Constitution 10)


---

### GLPF 용어/정책 ID 최소 정의 목록(본 섹션 범위)
- `oracle_ref_id`: Oracle 라운드 레코드 집합을 가리키는 Ref ID(2614/2616 규칙 적용). [REFERENCE_REQUIRED]
- `oracle_round`: 트랜잭션에서 지정하는 오라클 라운드 식별자(결정적 입력). [REFERENCE_REQUIRED]
- `ownership_domain_ref_id`: NFT/Ownership 검증 도메인 및 정책 레지스트리 참조. [REFERENCE_REQUIRED]
- `protocol_liquidity_matching_policy_id`: NFT 단독 예치 시 반대편 유동성 매칭 규칙의 정책 ID. [REFERENCE_REQUIRED]
- `segregation_policy_id`: Vault 분리 및 라우팅 edge 허용 규칙 정책 ID. [REFERENCE_REQUIRED]
- `valuation_policy_id`: NFT Principal/Premium 평가 및 haircut 규칙 정책 ID. [REFERENCE_REQUIRED]
- `nft_policy_id`: NFT 취급 범위(scope) 및 허용 상태 검증 정책 ID. [REFERENCE_REQUIRED]
- `transfer_policy_id`: Position/Pool 전송 제한 및 수혜자 적격성 정책 ID. [REFERENCE_REQUIRED]
- `time_ref`: 합의적으로 재현 가능한 시간/순번 참조값(tx_digest/checkpoint 기반). [REFERENCE_REQUIRED]

<-bash: cd: /home/boshin57/tobmate-agent-factory: No such file or SOURCE: workspace/drafts/3O_2621_2630_approved.md -->
## 2621. PoolFactory/Registry: 풀 생성 권한 및 네임스페이스

### Purpose
1. Gold Liquidity Pool Framework(GLPF)에서 풀(Pool)의 생성·등록·중복방지·검색 가능성을 결정론적(deterministic)으로 보장한다.
2. 풀 생성 행위가 Execution Authorization Framework(EAF) 및 Business Rule Validation Framework(BRVF)를 통과하지 않으면 어떠한 상태도 생성되지 않도록 한다.
3. 동일 풀 Key의 중복 생성 가능성은 거버넌스 정책(Governance Policy)으로 제한·통제한다.

### Architecture or Rule
1. **PoolFactory**는 풀 생성 트랜잭션의 단일 진입점(entry)이며, **PoolRegistry**는 생성된 풀의 네임스페이스 및 인덱스의 정합성 기준점(canonical index)이다.
2. 풀의 정체성(Identity)은 다음 **Pool Key**로 정의한다.
   1) Network ID  
   2) Asset A Type  
   3) Asset B Type  
   4) Pool Type (예: Constant Product, Stable Curve, Weighted, Hybrid NFT·FT)  
   5) Fee Tier
3. 동일 Pool Key의 중복 풀 생성 허용 여부는 **Governance Policy**로 제어하며, 기본값은 `deny`로 한다(명시적 승인 없이는 중복 생성 불가).
4. Asset Pair는 **Canonical Asset Order(Section 2622)** 적용 후 Key를 구성해야 한다.
5. PoolRegistry는 “풀 객체의 존재”만이 아니라 “키→풀ID 매핑의 유일성”을 강제하는 기준 데이터로 간주한다(프론트/인덱서 보조 데이터는 감사 대상으로만 취급).
6. 표준 실행 파이프라인은 항상 다음 순서를 따른다: **EAF → BRVF → Atomic Execution → Commit → Audit**.

### State/Flow
1. 입력: `(network_id, asset_x_type, asset_y_type, pool_type, fee_tier, init_liquidity, init_price_params, policies_ref)`
2. (Read-only Pre-derivation) 정렬 및 파생값 계산(읽기 전용):
   1) `asset_a_type, asset_b_type := canonical_sort(asset_x_type, asset_y_type)` (Section 2622)
   2) `pool_key := hash(network_id || asset_a_type || asset_b_type || pool_type || fee_tier)`
   3) `existing := PoolRegistry.key_to_pool_id[pool_key]` 조회(읽기 전용)
   - 본 단계는 **읽기 전용 조회 및 결정론적 파생값 계산**만 수행하며, 권한 의존 결론(예: DAO 승인 필요의 최종 확정)이나 상태변경을 수행하지 않는다.
3. EAF 승인
4. BRVF 검증
5. Atomic Execution:
   1) 중복 방지 적용: `existing`이 존재하고 `allow_duplicate=false`이면 즉시 실패
   2) Pool object 생성 + Registry 반영 + 이벤트 기록(모두 원자적)
6. Commit
7. Audit(커밋 결과에 대한 감사 레코드 확정)

### Validation
1. 결정론:
   1) Key 구성 요소는 모두 온체인 데이터(또는 트랜잭션 입력)로 고정되어야 한다.
   2) 동일 입력은 동일 Key를 산출해야 한다.
2. 중복 방지:
   1) `allow_duplicate=false`에서 동일 Key의 `key_to_pool_id`가 이미 존재하면 생성 불가
   2) `allow_duplicate=true` 경로는 **[REFERENCE_REQUIRED]**(결정론적 충돌해소/네임스페이스 규칙) 확정 전까지 **비활성화(deny-by-default)** 한다.
3. 네임스페이스 무결성:
   1) Registry의 `key_to_pool_id`와 실제 Pool object의 `pool_key`는 항상 일치해야 한다.

### Failure handling
1. `E1005 Policy Not Found`: 필요한 Governance Policy/Pool Policy 참조가 없을 때
2. `E1007 Business Rule Violation`: 중복 생성 금지 위반 또는 네임스페이스 규칙 위반
3. `E1008 Invalid Object State`: Registry 무결성 위반(키는 있으나 풀 객체가 없음 등) 탐지 시 CreatePool은 즉시 실패하며, 복구는 운영자 EAF 권한 하의 별도 절차로만 수행한다([REFERENCE_REQUIRED]: Registry Repair Procedure).
   - CreatePool 트랜잭션 내에서 “감사 플래그 기록”을 위한 추가 온체인 상태변경은 금지한다(원자성/무부분상태 원칙).

### Audit
1. PoolRegistry 변경은 반드시 이벤트 및 감사레코드(Audit Record)를 남겨야 한다(커밋된 상태에 한함).
2. 감사 필드 최소 요건:
   1) `pool_key, pool_id, caller, eaf_auth_id, brvf_rule_set_id, timestamp_ms`

### Invariants
1. (Determinism) 동일 입력에 대해 `pool_key`는 항상 동일하다.
2. (Uniqueness) `allow_duplicate=false`일 때 `pool_key`는 최대 1개의 풀에만 매핑된다.
3. (Authorization-First) EAF/BRVF 통과 없이 Registry에 어떤 매핑도 추가될 수 없다.


---

## 2622. 허용 자산(whitelist)과 Reserve-backed 자산 검증 흐름

### Purpose
1. 풀에 포함될 수 있는 자산 타입(Type)이 승인 목록(whitelist) 및 Reserve-backed 제약을 만족함을 보장한다.
2. Verified physical reserve가 발행(issuance)에 선행해야 하며, 준비금 참조 없는 GOLDPEG 유사 자산의 임의 유동성화를 차단한다.

### Architecture or Rule
1. 자산 검증은 다음 2계층으로 구성한다.
   1) **Asset Whitelist Policy**: 풀에서 거래 가능한 Type의 범주 승인
   2) **Reserve-backed Validation**: GOLDPEG 등 준비금 기반 자산이 GRBF의 Verified Reserve 참조 규칙을 만족하는지 검증
2. 자산 분류(예):
   1) Reserve-backed FT (예: GOLDPEG)
   2) 승인 Stable Asset(USD stable 등)
   3) Native Token
   4) 승인 NFT(하이브리드 풀의 Gold NFT 등)
3. 풀 생성 시, Asset A/B 각각에 대해 다음이 충족되어야 한다.
   1) whitelist 상 “pool_type별 허용”이 참이어야 한다.
   2) reserve-backed 자산이면 “정책 포인터 존재”는 필요조건이며, 추가로 **온체인 Verified Reserve 상태**가 결정론적으로 검증되어야 한다.
4. **Canonical Asset Order(단일 정의)**:
   1) `type_hash(asset_x_type) < type_hash(asset_y_type)`이면 `(asset_a_type, asset_b_type) := (asset_x_type, asset_y_type)`
   2) 그렇지 않으면 swap하여 `(asset_a_type, asset_b_type) := (asset_y_type, asset_x_type)`
   3) 여기서 `type_hash`는 온체인에서 결정론적으로 계산되는 Type 식별 해시이며, 동일 Type에 대해 항상 동일 결과여야 한다.
   4) 이 정렬 결과는 Pool Key 구성에 사용되는 유일한 순서이다.

### State/Flow
1. 입력 자산 타입 수신
2. Canonical Asset Order 적용(본 Section)
3. Whitelist 확인:
   1) `AllowedAssetPolicy.is_allowed(asset_type, pool_type) == true`
4. Reserve-backed 검증(해당 자산에 한함):
   1) `reserve_policy_id` 및 `reserve_reference_id`(예: GRBF가 관리하는 Reserve Object ID 또는 Reserve Anchor ID) 존재
   2) GRBF 결정론적 조회 경로로 `reserve_reference_id`를 역참조하여 `verified_state == VERIFIED`(또는 발행/유통 허용 상태)임을 검증
   3) `proof_digest/audit_anchor`(감사 앵커) 값이 GRBF 상태와 일치함을 검증(정합성)
   4) 정책 버전 및 상태가 유효(활성, 만료/폐기 아님)
5. 통과 후에만 다음 단계(초기 유동성/가격 검증) 진행

### Validation
1. `oracle_policy_id`가 요구되는 풀 타입(예: Stable Curve, Oracle Guard 활성 풀)인 경우, 누락 시 실패
2. reserve-backed 자산인데 다음 중 하나라도 불충족이면 실패:
   1) `reserve_reference_id` 부재
   2) GRBF 조회 불가(결정론적 경로 부재)
   3) `verified_state != VERIFIED`(또는 정책상 유통/유동성화 불가 상태)
   4) `proof_digest/audit_anchor` 불일치
3. Asset 정렬 결과가 입력 순서와 무관하게 항상 동일해야 함

### Failure handling
1. `E1005 Policy Not Found`: whitelist/asset policy/oracle policy/reserve policy 미존재
2. `E1006 Policy Version Mismatch`: 정책 버전 불일치
3. `E1007 Business Rule Violation`: 비허용 자산, reserve-backed 검증 실패, canonical order 위반

### Audit
1. 풀 생성 시 자산 검증 결과를 감사 레코드로 남긴다.
2. 최소 필드:
   1) `asset_a_type, asset_b_type, pool_type, fee_tier`
   2) `whitelist_policy_id, reserve_policy_id(optional), reserve_reference_id(optional), reserve_audit_anchor(optional), oracle_policy_id(optional)`
   3) `validation_result_code`

### Invariants
1. (Reserve-First) Verified Reserve의 결정론적 참조/검증이 불가능한 reserve-backed 자산은 풀 생성 불가
2. (Canonical Order) 동일 자산쌍은 항상 동일한 (A,B) 순서를 갖는다


---

## 2623. 초기 유동성 부여(bootstrap)와 초기 가격 설정 규칙

### Purpose
1. 풀 생성 직후 가격 형성(price discovery)이 조작되지 않도록 초기 유동성 및 초기 가격 설정을 제한한다.
2. 초기 유동성 공급(bootstrap)이 감사 가능하고, 후속 스왑/LP 단위 회계의 기준점이 되도록 한다.

### Architecture or Rule
1. 풀 생성은 반드시 “초기 유동성(initial liquidity)”을 포함해야 하며, `Minimum Initial Liquidity`를 하회하면 실패한다.
2. 초기 가격 설정은 다음 중 최소 1개 이상을 사용해야 한다.
   1) Reference Oracle 기반 fair value range
   2) Governance-approved bootstrap(사전 승인된 초기 가격/범위/지연 조건)
3. 초기 가격 조작 방지 가드(Oracle Guard)는 다음 파라미터로 구성한다.
   1) `fair_value_min`, `fair_value_max`
   2) `maximum_initial_deviation_bps`
   3) `initialization_delay_ms`(필요 시)
4. 초기 유동성 입금은 풀 타입별로 정의된 자산 구성 규칙을 만족해야 한다(예: Weighted는 가중치 비율).
5. 자산 이동(초기 유동성 입금)은 **Atomic Execution** 단계의 일부로 수행한다. EAF는 “이동 권한(capability)”을, BRVF는 “경제 규칙 적합성(최소치/구성/정책)”을 분리 검증한다.

### State/Flow
1. `init_liquidity` 수신(Asset A/B 입금, 필요 시 추가 자산)
2. 최소 유동성 체크:
   1) `amount_a >= min_a` 및 `amount_b >= min_b` 또는 풀 정책이 정의한 단일 기준(`min_value_usd`) 충족
3. 초기 가격 파라미터 산출:
   1) `init_price := amount_b / amount_a` 등 모델별 정의
   2) 가격 수학(Price Math) 스케일/반올림 규칙은 **[REFERENCE_REQUIRED]: Price Math Spec** 확정 전까지 Oracle Guard 필수 풀을 제외하고는 생성이 제한될 수 있으며(정책), 최소한 **결정론적 정수 나눗셈 및 반올림 방향**을 고정해야 한다(본 장에서는 “풀 보호 방향” 우선).
4. Oracle Guard 검증(Section 2628)
5. 통과 시 Pool object의 초기 reserve, price accumulator 초기화, LP 포지션 민팅 진행

### Validation
1. `Minimum Initial Liquidity` 위반 시 실패
2. 초기 가격이 허용 편차를 초과하면 실패
3. initialization_delay가 설정된 경우:
   1) 생성 즉시 `swaps_enabled=false`로 초기화
   2) 지연 종료 전 swap은 BRVF에서 거절되어야 함([REFERENCE_REQUIRED]: swap 섹션)  
   3) 상기 참조가 확정되기 전까지는 **지연 모델을 사용하는 풀은 swaps를 기본 비활성화로 생성하며, 활성화 전이는 별도 승인 트랜잭션으로만 허용**한다(deny-by-default).

### Failure handling
1. `E1007 Business Rule Violation`: 최소 유동성 위반, 초기 가격 범위 위반, 부트스트랩 정책 위반
2. `E1008 Invalid Object State`: 풀 정책상 요구 자산이 누락된 경우
3. 자산 이동 실패의 오류 매핑은 공통 오류코드 레지스트리에 따른다([REFERENCE_REQUIRED]: Common Error Code Registry). 참조 확정 전까지는 “자산 이동 실패=트랜잭션 실패(롤백)”로만 처리한다.

### Audit
1. 초기 유동성 및 초기 가격 산출 근거 기록:
   1) `init_amount_a, init_amount_b, init_price`
   2) `oracle_price(optional), deviation_bps(optional)`
   3) `bootstrap_policy_id(optional)`

### Invariants
1. (Bootstrap Integrity) `liquidity_enabled=true`로 생성되는 모든 풀은 생성 커밋 시점에 `reserve_a>0` 및 `reserve_b>0`을 만족해야 한다(Weighted/Hybrid 등 다자산은 해당 모델이 요구하는 “모든 필수 구성자산 reserve>0”으로 일반화).
2. (Manipulation Guard) oracle 기반 초기 가격 허용 범위를 벗어난 생성은 불가하다.


---

## 2624. 수수료 티어(Fee Tier) 및 파라미터 거버넌스 연결점

### Purpose
1. Fee Tier 및 핵심 파라미터가 임의로 설정되어 LP/사용자/준비금 안정성을 훼손하는 것을 방지한다.
2. 파라미터는 거버넌스 정책에 의해 버전 관리되며, 풀은 참조만 한다.

### Architecture or Rule
1. 풀은 `fee_policy_id`를 필수로 가진다.
2. Fee Policy는 최소 다음을 포함해야 한다(정확 필드는 정책 모듈에 종속, 본 섹션에서는 인터페이스 요구만 정의).
   1) `fee_tier`(예: bps)
   2) `protocol_fee_share`(프로토콜 수수료 비율)
   3) `lp_fee_share`
   4) `max_fee_cap`
   5) `effective_date/version`
3. Oracle Guard 또는 TWAP을 요구하는 풀은 `oracle_policy_id: Option<ID>`를 가진다.
4. Fee Tier/Policy 변경은 풀 생성 시점에 고정 참조(pinned reference)하거나, 정책이 허용하는 경우에만 업그레이드 가능해야 한다(업그레이드 방식은 [REFERENCE_REQUIRED]).

### State/Flow
1. 입력 `fee_tier` → `FeePolicyRegistry.resolve(fee_tier, pool_type, asset_pair_class)` → `fee_policy_id`
2. `oracle_policy_id` 필요 여부 결정:
   1) Stable Curve 또는 Oracle Guard 활성 풀 → 필수
   2) Constant Product 기본 풀 → 선택(단, governance가 강제할 수 있음)
3. Pool object에 `fee_policy_id`, `oracle_policy_id` 저장

### Validation
1. `fee_policy_id` 미존재/비활성 → 실패
2. `fee_tier`가 `max_fee_cap` 초과 → 실패
3. oracle 필수 풀에서 `oracle_policy_id=None` → 실패
4. 수수료 분배 정규화:
   1) `protocol_fee_share + lp_fee_share == 1`(또는 `10000bps`)를 만족해야 하며, 각 항은 정책이 정의한 범위 내여야 한다.

### Failure handling
1. `E1005 Policy Not Found`
2. `E1006 Policy Version Mismatch`
3. `E1007 Business Rule Violation`

### Audit
1. 풀 생성 감사 레코드에 다음을 포함:
   1) `fee_tier, fee_policy_id, oracle_policy_id(optional)`
   2) `policy_version`

### Invariants
1. (Governance Anchoring) 풀의 fee 관련 값은 거버넌스 정책 참조 없이 임의 설정될 수 없다.
2. (Cap Safety) 상한을 초과하는 수수료 티어는 어떤 풀에서도 활성화될 수 없다.
3. (Fee Normalization) `protocol_fee_share`와 `lp_fee_share`는 정책 단위에서 정규화되어야 하며, 풀은 이를 위반하는 정책을 참조할 수 없다.


---

## 2625. BRVF 검증 항목(준비금 참조, 권리 분리, 파라미터 범위)

### Purpose
1. 풀 생성 상태전이가 “무엇을 실행할 수 있는가(What Can Execute)”의 관점에서 합법적임을 BRVF가 표준화된 규칙으로 검증한다.
2. 준비금, 권리 분리(NFT principal vs FT utilization), 파라미터 범위, 결정론을 침해하는 풀 생성을 차단한다.

### Architecture or Rule
1. BRVF는 `Operation=CreatePool`에 대해 다음 Rule Set을 수행한다.
   1) Asset Rules: whitelist 및 asset class 적합성
   2) Reserve Rules: reserve-backed 자산의 Verified Reserve 결정론적 참조 및 상태 검증
   3) Liquidity Rules: 최소 유동성, 초기 가격 가드, 풀 타입 적합성
   4) Parameter Rules: fee/oracle/curve/weight 파라미터 범위
   5) Rights Separation Rules: NFT/FT 권리 혼합으로 원금 소유권(NFT) 침해 가능성 차단
2. Hybrid NFT·FT 풀의 경우, 본 장의 안전 기본값은 다음과 같다.
   1) **[REFERENCE_REQUIRED]: Hybrid pool 상세 모델** 및 관련 권리/수탁/분쟁/보험/Exit Queue 사양이 확정되기 전까지, Hybrid 타입 풀은 **생성 불가(deny-by-default)** 로 처리한다.
   2) 다만 거버넌스가 예외적으로 활성화하는 경우에도, CreatePool/Bootstrap 단계에서 다음 최소 불변 검증을 강제한다.
      - (Principal Non-dilution) Principal NFT는 CreatePool/Bootstrap 과정에서 **묵시적 이전/소각/병합(burn/merge)** 될 수 없다.
      - (Explicit Transfer Only) Principal NFT의 소유자(owner) 변경이 발생하는 상태전이는 반드시 **명시적 서명 기반 이전(transfer)** 로만 허용되며, LP 발행과 결합된 자동 교환을 금지한다.
      - (Economic Right Only) LP Position은 “economic utilization right”만 표현하며 Principal NFT에 대한 소유권 자체를 대체하지 않는다.
      - (Custody/Escrow Required) NFT가 풀에 “예치”되는 경우, Principal NFT는 별도의 custody/escrow 객체에 잠금(lock)되어야 하며, 해당 custody 객체는 감사 앵커(audit anchor)를 남겨야 한다.
3. 누적가격(cumulative price) 및 시간 관련 값은 실제 지원 정수 타입 및 프레임워크 API에 맞춰 결정론적으로 초기화되어야 한다.
   1) 예: `cumulative_price_a: u256`, `cumulative_price_b: u256`, `last_price_update_ms: u64`

### State/Flow
1. CreatePool 요청 수신
2. BRVF Rule Engine이 Rule Registry에서 `CreatePool` 규칙 버전을 조회
3. 규칙 실행 순서(권장):
   1) Pair/Type 정렬 및 정책 조회
   2) reserve-backed 검증(Verified Reserve 포함)
   3) 초기 유동성·초기 가격 검증
   4) 파라미터 범위 검증
   5) Hybrid인 경우(활성화된 경우에 한함) NFT eligibility 및 권리 분리 최소 불변 검증
4. 통과 시 `Valid State Transition` 토큰(논리적 승인)을 원자 실행 단계로 전달

### Validation
1. 규칙 버전:
   1) `rule_set_id` 및 `schema_version` 불일치 시 실패
2. 결정론:
   1) 시간값은 트랜잭션 컨텍스트에서 제공되는 단일 기준을 사용해야 함(노드별 변동값 사용 금지)
3. 권리 분리:
   1) Principal NFT를 FT로 대체하거나 소각/재할당하는 전이를 포함하면 실패
   2) LP Position이 Principal NFT의 소유권을 표현하거나, Principal NFT의 권리를 “침묵적으로” 잠식하는 파생권 생성은 실패

### Failure handling
1. `E1006 Policy Version Mismatch`
2. `E1007 Business Rule Violation`
3. `E1010 Replay Attack Detected`: 동일 CreatePool 요청의 재사용 방지 토큰/nonce 정책 위반 시(적용 시)

### Audit
1. BRVF 실행 결과는 다음을 기록:
   1) `rule_set_id, rule_version, validation_hash`
   2) `inputs_digest(pool_key, policies_ref_digest)`
   3) `result_code, failed_rule(optional)`

### Invariants
1. (Rule Gate) BRVF 통과 없는 풀 생성 커밋은 불가하다.
2. (Rights Separation) 원금 소유권 NFT와 경제적 활용 FT의 권리가 풀 생성 과정에서 혼합되지 않는다.


---

## 2626. EAF 승인 정책(누가 어떤 풀을 만들 수 있는가)

### Purpose
1. 풀 생성 권한을 역할·정책 기반으로 통제하여, 무분별한 풀 생성 및 공격 표면을 감소시킨다.
2. EAF가 “Who Can Execute”를 표준 카테고리로 검증하고, BRVF와 결합하여 원자 실행 전 승인을 완결한다.

### Architecture or Rule
1. EAF는 `CreatePool` 실행에 대해 최소 다음 Authorization Category를 적용한다([TABLE 1] 범주 사용).
   1) Identity Authorization: 호출자 TMID 유효성
   2) Object Authorization: PoolFactory/Registry 변경 권한
   3) Liquidity Authorization: 초기 유동성 제공 자산 이동 권한(capability)
   4) Financial Authorization: FT/GOLDPEG 이동 권한(해당 시)
   5) Reserve Authorization: reserve-backed 자산이 포함되고 정책이 요구하는 경우, 준비금 참조 정책 접근 권한
   6) DAO Authorization: 거버넌스 승인 풀 타입(Weighted, Hybrid 등)인 경우 필수
   7) Emergency Authorization: 시스템이 생성 동결(freeze) 상태인 경우 차단 또는 예외 승인
2. 풀 타입별 권한 정책:
   1) Constant Product(기본): “허용된 자산쌍 + 표준 Fee Tier”에 한해 Permissionless를 거버넌스가 허용할 수 있다.
   2) Stable Curve: Oracle Policy 승인 및 위험 파라미터 승인 필요(DAO/Risk Governance)
   3) Weighted/Hybrid: 기본적으로 Governance 승인 필요
3. 표준 파이프라인은 항상 다음 순서를 따른다: **EAF → BRVF → Atomic Execution → Commit → Audit**.

### State/Flow
1. `CreatePool` 엔트리 호출
2. EAF 검증:
   1) caller identity, capability, policy scope
   2) DAO 승인 필요 여부 판정 및 증빙 확인
3. EAF 통과 → BRVF 호출 → 통과 → Atomic Execution → Commit → Audit

### Validation
1. caller가 요구 capability를 제시하지 못하면 실패
2. DAO 승인(required)인데 승인 증빙(예: proposal execution proof)이 없으면 실패([REFERENCE_REQUIRED]: DAO 승인 증빙 객체)  
   - 참조 사양 확정 전까지는 “DAO 승인 필요 풀 타입”은 **생성 불가(deny-by-default)** 로 처리한다(예외 실행 금지).

### Failure handling
1. `E1001 Invalid TMID`
2. `E1002 Unauthorized Caller`
3. `E1003 Invalid Capability`
4. `E1004 Permission Denied`
5. `E1009 Authorization Expired`

### Audit
1. EAF 승인 기록:
   1) `auth_categories_applied, capability_ids, dao_approval_ref(optional), timestamp_ms`
2. 승인과 BRVF 결과를 동일 트랜잭션 감사 번들로 연결:
   1) `eaf_auth_id` ↔ `brvf_validation_hash`

### Invariants
1. (Authorization Gate) EAF 승인 없는 풀 생성 커밋은 불가하다.
2. (Governance Segregation) 고위험 풀 타입(Weighted/Hybrid/Oracle 의존)은 거버넌스 승인 없이 생성될 수 없다.


---

## 2627. Pool 생성 Flow(End-to-End) 및 표준 이벤트

### Purpose
1. 풀 생성 절차를 표준화하여 구현체가 동일한 상태전이와 감사 로그를 생성하도록 한다.
2. 풀 생성 실패 시 부분 상태(partial state)가 남지 않도록 원자성(atomicity)을 강제한다.

### Architecture or Rule
1. 표준 생성 Flow는 다음 순서를 따른다(원자 실행 단위).
   1) Approved Asset Pair 확인  
   2) Pool Type 확인  
   3) Fee Policy 확인  
   4) Oracle Policy 확인  
   5) Initial Liquidity 제공  
   6) Initial Price 검증  
   7) Pool Object 생성  
   8) LP Position 생성  
   9) PoolCreated Event
2. Pool Object의 최소 필드(발췌, 구현 언어의 실제 타입에 맞춰 조정):
   1) `pool_id: ID`
   2) `network_id: u64`
   3) `asset_a_type: Type`
   4) `asset_b_type: Type`
   5) `pool_type: u8`
   6) `fee_policy_id: ID`
   7) `oracle_policy_id: Option<ID>`
   8) `reserve_a: u128|u256` , `reserve_b: u128|u256`(정책에 따른 타입)
   9) `cumulative_price_a: u256`, `cumulative_price_b: u256`
   10) `last_price_update_ms: u64`
   11) `schema_version: u64`, `generation: u64`
   12) `swaps_enabled: bool`, `liquidity_enabled: bool`
   13) `status: u8`
3. 누적가격(cumulative price) 형식은 지원 정수 타입 및 프레임워크 API에 맞춰 조정하되, 반올림/스케일 규칙은 결정론적으로 고정되어야 한다.
   1) **[REFERENCE_REQUIRED]: TWAP/Oracle 누적값 계산 규칙**
   2) **[REFERENCE_REQUIRED]: Price Math Spec**
   - 상기 참조 사양 확정 전까지, 누적값 의존 기능(TWAP 기반 가드/스왑)은 **기본 비활성화(swaps_disabled 또는 guard_strict_fail)** 정책을 적용한다(deny-by-default).

### State/Flow
1. (Read-only Pre-derivation) Registry/정렬/정책조회(읽기 전용 + 결정론적 파생값 계산)
2. EAF 승인
3. BRVF 검증
4. Atomic Execution:
   1) 자산 이동(초기 유동성 입금)
   2) Pool object 생성 및 초기화
   3) LP Position object 생성(초기 공급자에게 귀속)
   4) Registry 등록
   5) Event emit
5. Commit
6. Audit

### Validation
1. 이벤트는 커밋된 상태와 1:1로 대응해야 한다(실패 트랜잭션에서 이벤트 발생 금지).
2. `swaps_enabled/liquidity_enabled` 초기값은 bootstrap 정책 및 initialization_delay에 의해 결정되어야 한다.
3. 자산 이동은 Atomic Execution에서 수행되며, 실패 시 전체 롤백된다(부분 상태 금지). 권한 부족은 EAF에서, 경제 규칙 위반은 BRVF에서 우선적으로 분리 검출되어야 한다(가능한 범위 내).

### Failure handling
1. 중간 단계 실패 시 전체 롤백(원자성)되어야 한다.
2. 정책 불일치/권한 부족/자산 이동 실패 시 해당 오류코드로 종료한다.
3. 자산 이동 실패 코드는 공통 레지스트리에 따른다([REFERENCE_REQUIRED]: Common Error Code Registry). 참조 확정 전까지는 “자산 이동 실패=트랜잭션 실패(롤백)”로만 처리한다.

### Audit
1. `PoolCreated` 이벤트(표준 필드):
   1) `pool_id, pool_key, asset_a_type, asset_b_type, pool_type, fee_tier, fee_policy_id, oracle_policy_id(optional)`
   2) `init_reserve_a, init_reserve_b, init_price`
   3) `creator, lp_position_id`
   4) `schema_version, timestamp_ms`

### Invariants
1. (Atomic Creation) Pool object, LP position, Registry 매핑, 이벤트는 모두 함께 커밋되거나 함께 롤백된다.
2. (Deterministic Init) 초기화 필드(누적가격/시간/상태)는 동일 정책 하에서 결정론적으로 설정된다.


---

## 2628. 초기 가격 조작 방지(Oracle Guard) 규칙

### Purpose
1. 풀 생성자가 비정상 Initial Price를 설정하여 LP 및 프로토콜을 손상시키는 것을 방지한다.
2. Oracle 기반 공정가(fair value) 범위 및 초기 유동성 최소치로 조작 비용을 증가시킨다.

### Architecture or Rule
1. Oracle Guard는 다음 요소를 지원한다.
   1) Reference Oracle
   2) Fair Value Range
   3) Minimum Initial Liquidity
   4) Maximum Initial Deviation
   5) Initialization Delay
   6) Governance-approved Bootstrap
2. 검증 규칙:
   1) `init_price`는 `oracle_price` 대비 `maximum_initial_deviation_bps` 이내여야 한다.
   2) `oracle_price`가 유효하지 않거나 stale이면(정책 정의) 생성 실패 또는 swaps 비활성으로 생성(정책 선택)한다.
   3) initialization_delay가 설정되면, 지연 기간 동안 swap을 비활성화한다.
3. 가격/편차 계산은 결정론적 Price Math 규격에 종속된다.
   1) **[REFERENCE_REQUIRED]: Price Math Spec**(고정소수점 스케일, 반올림, 오버플로 처리)
   2) 참조 확정 전까지는 deviation 계산을 요구하는 Oracle Guard 활성 풀은 **생성 불가(deny-by-default)** 또는 `swaps_enabled=false` 고정 생성만 허용한다(정책).

### State/Flow
1. Oracle price 조회(oracle_policy_id)
2. fair value range 산출(oracle_price 기반 또는 정책 고정 범위)
3. init_price deviation 계산
4. deviation 통과 + 최소 유동성 통과 시 생성 허용
5. delay 조건 반영하여 `swaps_enabled` 초기값 결정

### Validation
1. oracle 응답의 freshness(최대 지연 ms)는 정책으로 정의되어야 한다.
2. deviation 계산 및 반올림/스케일은 **Price Math Spec**에 의해 결정론적으로 고정되어야 한다([REFERENCE_REQUIRED]).

### Failure handling
1. `E1007 Business Rule Violation`: deviation 초과, oracle stale, bootstrap 위반

### Audit
1. oracle 입력 및 deviation 계산 근거:
   1) `oracle_price, oracle_timestamp_ms, init_price, deviation_bps, guard_params_id`

### Invariants
1. (No Abnormal Init) 공정가 범위를 벗어난 초기 가격으로 풀을 생성할 수 없다(정책이 예외를 허용하지 않는 한).


---

## 2629. 수학 모델 선택(상수곱/스테이블/가중/하이브리드)과 초기 파라미터 범위

### Purpose
1. 풀 타입(Pool Type)별로 허용되는 초기 파라미터 범위를 규정하여 위험한 설정을 차단한다.
2. 모델별 핵심 불변식(invariant)이 생성 시점부터 성립하도록 한다.

### Architecture or Rule
1. Constant Product Model:
   1) 기본식: `x * y = k`
   2) 출력 계산은 Pool 보호 방향 반올림을 사용:
      - Trader Output: Downward Rounding
      - Required Input: Upward Rounding
2. Stable Curve:
   1) GOLDPEG–금/또는 USD 기준 stable asset에 적용 가능
   2) GOLDPEG와 USD stable은 동일가치가 아니므로 Gold Price Oracle 및 curve parameter를 함께 사용해야 한다.
3. Weighted Pool:
   1) Basket/Treasury liquidity에 사용 가능
   2) 초기 단계에서는 Governance 승인 풀에만 적용
4. Hybrid NFT·FT Pool:
   1) 일반 FT 풀과 구분된 풀 타입으로 생성되어야 하며, Eligibility/Exit Queue/Dispute Lock 등 추가 상태를 요구한다([REFERENCE_REQUIRED]).
   2) 해당 참조 확정 전까지 Hybrid 타입은 **생성 불가(deny-by-default)** 로 처리한다(Section 2625와 동일).

### State/Flow
1. `pool_type`에 따라 `required_params_schema` 선택
2. 파라미터 디코딩 및 범위 검증
3. 모델 불변식이 성립하는 초기 reserve/weight/amp 등 검증
4. 통과 시 Pool object에 파라미터 고정 저장

### Validation
1. Constant Product:
   1) reserve 0 금지(정책 예외 없으면)
2. Stable Curve:
   1) oracle_policy_id 필수
   2) amp/parameter 범위는 governance 정책 범위 내
3. Weighted:
   1) weight 합=1(또는 정규화 규칙) 및 최소 weight 제한
   2) governance 승인 증빙 필요([REFERENCE_REQUIRED]: DAO 승인 증빙 객체). 참조 확정 전까지는 **생성 불가(deny-by-default)**.

### Failure handling
1. `E1007 Business Rule Violation`: 파라미터 범위 위반, 모델 불변식 위반

### Audit
1. `pool_type, params_digest, params_version, governance_approval_ref(optional)`

### Invariants
1. (Model Integrity) 선택된 모델의 초기 불변식이 생성 시점부터 성립해야 한다.
2. (Rounding Safety) 반올림 규칙은 항상 풀 보호 방향으로 고정된다.


---

## 2630. 풀 상태(Status) 초기화, 활성화 플래그, 및 생성 후 변경 제한

### Purpose
1. 생성 직후 풀의 상태(status) 및 기능 플래그(swaps_enabled/liquidity_enabled)를 표준화하여, 초기화 지연 및 비상 정책을 일관되게 적용한다.
2. 생성 후 정책 변경이 원금 소유권, 준비금, 감사 불변식을 침해하지 않도록 변경 제한을 둔다.

### Architecture or Rule
1. Pool status는 최소 다음 상태를 지원한다(정수 `status: u8`로 표현 가능).
   1) `BOOTSTRAP`(초기화/지연)
   2) `ACTIVE`
   3) `FROZEN`
   4) `DEPRECATED`
2. 초기 값 결정 규칙:
   1) initialization_delay가 없고 모든 가드 통과 → `status=ACTIVE`, `swaps_enabled=true`, `liquidity_enabled=true`
   2) initialization_delay 존재 → `status=BOOTSTRAP`, `swaps_enabled=false`, `liquidity_enabled=true`(정책에 따름)
   3) Emergency freeze가 활성 정책이면 생성 자체가 차단되거나 `FROZEN`으로 생성(정책 선택)
3. 생성 후 변경 제한:
   1) `fee_policy_id`, `oracle_policy_id` 변경은 거버넌스 정책 및 EAF 권한 없이는 불가
   2) status 전이는 EAF의 Emergency/DAO 권한과 BRVF의 상태전이 규칙을 동시에 만족해야 한다.
   3) [REFERENCE_REQUIRED] 항목(상태전이 표, Price/TWAP 사양, DAO 승인 증빙)이 확정되기 전까지는, `BOOTSTRAP → ACTIVE` 자동 전이를 금지하고 **명시적 승인 트랜잭션 + 정책 검증** 없이는 활성화를 허용하지 않는다(deny-by-default).

### State/Flow
1. CreatePool 커밋 시 status/flags 초기화
2. (옵션) 지연 만료 후 `BOOTSTRAP → ACTIVE` 전이:
   1) EAF 승인(운영자/정책에 따른 자동 실행 주체)
   2) BRVF: 시간 조건 및 oracle freshness 재검증
   3) 커밋 후 swaps_enabled 활성

### Validation
1. status 전이 표는 정책으로 제한되어야 한다([REFERENCE_REQUIRED]: 상태전이 표). 참조 확정 전까지는 상태전이를 최소 집합으로 제한한다(예: `ACTIVE↔FROZEN`도 거버넌스/비상 권한에 한정).
2. 동일 트랜잭션에서 status를 우회하여 swaps_enabled를 true로 만들 수 없다.

### Failure handling
1. `E1004 Permission Denied`: 비상/DAO 권한 부족
2. `E1007 Business Rule Violation`: 부적절한 status 전이, 지연 조건 위반
3. `E1008 Invalid Object State`: flags/status 불일치 탐지

### Audit
1. status/flags 변경 이벤트(표준):
   1) `PoolStatusChanged { pool_id, old_status, new_status, swaps_enabled, liquidity_enabled, reason_code, approver_ref }`

### Invariants
1. (No Bypass) 초기화 지연 또는 freeze 정책을 우회하여 스왑을 활성화할 수 없다.
2. (Deterministic Flags) status/flags는 정책 입력과 검증 결과에 의해 결정론적으로 설정된다.

<-bash: cd: /home/boshin57/tobmate-agent-factory: No such file or SOURCE: workspace/drafts/3O_2631_2640_approved.md -->
```markdown
## 2631. 목적 (Purpose)

2631.1 본 절은 Gold Liquidity Pool Framework(GLPF)에서 LP 참여의 핵심 트랜잭션인 예치(Add Liquidity) 및 회수(Remove Liquidity)에 대한 상태기계(State Machine), 회계(Accounting) 모델, 검증(Validation), 권한(Execution Authorization), 실패 처리(Failure Handling), 감사(Audit) 및 불변식(Invariants)을 정의한다.

2631.2 본 절은 다음 헌법적 제약을 전제로 한다.  
1) 준비금(Verified Reserve) 우회 발행·유동성 생성 금지  
2) 원금 소유권(Principal Ownership) 권리의 비가시적 희석/재배정/소각 금지  
3) 권리 분리: 원금 소유권 NFT와 경제적 활용 FT의 분리  
4) 모든 상태전이는 BRV(Business Rule Validation) 및 EAF(Execution Authorization)를 통과해야 함  
5) 결정론적 상태(Deterministic canonical ledger state) 유지  
6) 수수료/보상은 정의된 가치원(Value Source)에 대응해야 함  
7) 재무 분리(Treasury/Insurance/Protocol Revenue/User Asset segregation)

---

## 2632. 아키텍처/규칙 (Architecture or Rule)

### 2632.1 객체 모델 (Object Model)

2632.1.1 `LiquidityPool<A,B>` (Shared Object) — 본 절에서는 FT-FT 풀의 Add/Remove에 필요한 최소 필드/불변만 요구한다.  
- 필수 필드(최소):  
  - `id: UID`  
  - `asset_a_type: TypeName`, `asset_b_type: TypeName`  
  - `reserve_a: u128`, `reserve_b: u128`  
  - `total_lp_units: u128`  
  - `locked_lp_units: u128` (영구 잠금 LP 단위; `minimum_locked_liquidity`의 on-chain 표현)  
  - `lp_fee_growth_global_a: u256`, `lp_fee_growth_global_b: u256` (LP Fee 전용 누적치)  
  - `status: u8` (ACTIVE/PAUSED/FROZEN 등)  
  - `oracle_guard_config_id: ID`  
  - `circuit_breaker_config_id: ID`  
  - `revenue_distribution_config_id: ID` (수익 라우팅 규칙 식별자; 실제 Vault들은 별도 프레임워크에서 분리 관리)

> 규범: 본 절의 LP Add/Remove는 어떠한 Vault(TreasuryVault/ProtocolRevenueVault/InsuranceReserveVault 등)로도 자금을 이동시키지 않는다. Vault 적립·분배는 MRDF/TRF/IRF 등 별도 프레임워크에서 정의되어야 한다([REFERENCE_REQUIRED]).

2632.1.2 `LiquidityPosition<A,B>` (Owned Object; Position NFT 성격)  
- 본 절은 다음 구조를 정규 모델로 사용한다(발췌 기반).  
```move
public struct LiquidityPosition<phantom A, phantom B> has key, store {
  id: UID,
  pool_id: ID,
  owner_tmid_id: ID,
  lp_units: u128,
  deposited_a: u128,
  deposited_b: u128,
  fee_growth_checkpoint_a: u256,
  fee_growth_checkpoint_b: u256,
  unclaimed_fee_a: u128,
  unclaimed_fee_b: u128,
  cost_basis_reference_id: Option<ID>,
  created_at_ms: u64,
  updated_at_ms: u64,
  generation: u64,
  status: u8,
}
```

2632.1.3 `LPActionReceipt` (성공 시 온체인 Receipt Object, 실패 시 Event)  
- “모든 개입에 Receipt 생성” 원칙은 다음과 같이 정규화한다.  
  - 성공(Success): 온체인 `LPActionReceipt` 객체를 생성한다.  
  - 실패(Failure/Abort): 온체인 객체는 생성되지 않으며, 표준 실패 이벤트(Failed Action Event)를 기록 대상으로 한다(오프체인 인덱싱 포함).  
- 필수 필드(성공 Receipt 최소):  
  - `id: UID`  
  - `workflow_id: vector<u8>` (업무 연결 키)  
  - `idempotency_key: vector<u8>` (재시도 안전성)  
  - `pool_id: ID`, `position_id: Option<ID>`  
  - `actor_tmid_id: ID`  
  - `action_type: u8` (ADD/REMOVE)  
  - `input_a: u128`, `input_b: u128` (ADD)  
  - `burn_lp_units: u128` (REMOVE)  
  - `min_output_a: u128`, `min_output_b: u128` (REMOVE)  
  - `actual_delta_reserve_a: i128`, `actual_delta_reserve_b: i128`  
  - `pre_state_hash: vector<u8>`, `post_state_hash: vector<u8>`  
  - `created_at_ms: u64`  
  - `result_code: u32` (0=success)  
  - `auth_context_digest: vector<u8>` (EAF 결과 요약)

2632.1.4 `FeeAccounting` (Pool 내부 필드 및 Position 필드로 구성)  
- `lp_fee_growth_global_*`(풀 전역 누적) + Position checkpoint 방식.  
- Position의 미청구 수수료는 `unclaimed_fee_*` 및 checkpoint 차이로 결정론적으로 계산 가능해야 한다.  
- 규범: 본 절에서 다루는 `lp_fee_growth_global_*`는 “LP Fee(유동성 제공 대가)”에 한정된다. Protocol Fee/Marketplace Fee/Insurance Allocation 등은 별도 누적·별도 회계·별도 분배 프레임워크에서 처리되어야 하며, LP 미청구 수수료에 혼입될 수 없다.

---

### 2632.2 상태 정의 (State)

2632.2.1 `LiquidityPosition.status`는 최소 다음을 포함한다.  
- `ACTIVE`: 보유 상태(회수 가능).  
- `LOCKED`: 회수 불가 상태(예: 담보, 규제 동결, 비상조치).  
- `CLOSED`: `lp_units = 0`이며 재활성화 불가.

> 규범: 본 절에서는 상태를 단순화하여 `ACTIVE`에서 RemoveLiquidity를 허용한다. 별도의 “회수 대기/큐” 상태 또는 Hybrid Exit 정책은 Hybrid NFT·FT Pool 절에서 정의한다([REFERENCE_REQUIRED]).

2632.2.2 상태 전이는 임의 set이 아니라 “전용 상태 전이 함수”로만 변경한다.

---

### 2632.3 권한/검증 프레임 (BRV + EAF)

2632.3.1 모든 Add/Remove는 아래 순서를 고정한다. 이때 Receipt/Event 기록은 곧 Audit Recording이며, 고정 순서의 “Audit Recording”에 해당한다.  
1) 입력 정규화 및 Idempotency 검증  
2) BRV 실행(정책/불변/수량/슬리피지/상태)  
3) EAF 실행(Identity/Ownership/Object/Financial/Liquidity/Validator/Emergency 등)  
4) 상태 갱신 및 자산 이동(원자적)  
5) Receipt/Event 기록(Audit Recording; 원자적)  
6) 실패 시 전체 Abort(부분 성공 금지)

2632.3.2 적용 권한 카테고리(최소):  
- Identity Authorization: `actor_tmid_id` 유효성  
- Ownership Authorization: Position 소유(REMOVE), 또는 새 Position 수령(ADD)  
- Object Authorization: Pool/Position 변경 권한  
- Financial Authorization: `Coin<A>`, `Coin<B>` 이동 권한  
- Liquidity Authorization: `lp_units` mint/burn 권한(풀 정책)  
- Validator Authorization: 공유 객체 변경에 필요한 합의 컨텍스트  
- Emergency Authorization: Pool PAUSED/FROZEN 시 제한

---

## 2633. AddLiquidity 트랜잭션 (State/Flow)

### 2633.1 목적

2633.1.1 사용자가 `LiquidityPool<A,B>`에 자산 `A,B`를 예치하고, 이에 상응하는 `lp_units`를 `LiquidityPosition<A,B>`로 발행/증가시키며, 수수료 누적 체크포인트를 설정한다.

### 2633.2 입력 (Command Inputs)

- `pool: &mut LiquidityPool<A,B>`  
- `actor_tmid_id: ID`  
- `position_opt: Option<LiquidityPosition<A,B>>` (없으면 신규 생성)  
- `coin_a_in: Coin<A>`, `coin_b_in: Coin<B>`  
- `max_input_a: u128`, `max_input_b: u128` (입력 상한)  
- `deadline_ms: u64`  
- `expected_ratio_x1e18: u128` (정규화 비율)  
- `max_slippage_bps: u16`  
- `idempotency_key: vector<u8>`  
- `workflow_id: vector<u8>`

### 2633.3 상태/흐름 (State/Flow)

2633.3.1 단계 A — 사전검증  
1) `pool.status == ACTIVE` 확인  
2) `now_ms <= deadline_ms` 확인  
3) `coin_a_in.amount <= max_input_a`, `coin_b_in.amount <= max_input_b` 확인  
4) 자산 Allowlist 및 Type 일치 확인(풀의 `asset_*_type`)  
5) Oracle Guard / Circuit Breaker 선검사(가격괴리, stale 등)  
   - Oracle Timestamp 초과 시 실패  
   - Circuit Breaker 발동 시 실패(정책 파라미터는 `circuit_breaker_config_id`에 의해 결정; 상세는 [REFERENCE_REQUIRED])

2633.3.2 단계 B — 비율 및 슬리피지 계산(결정론 규칙 포함)  
1) 결정론적 고정소수점 규칙  
   - 스케일: `x1e18` 고정소수점 사용  
   - 반올림: 모든 나눗셈은 `floor`(내림) 적용  
   - 오버플로/0 나눗셈: 즉시 Abort  
2) 비율 정의  
   - `actual_ratio_x1e18 = floor(deposit_a * 1e18 / deposit_b)` (단, `deposit_b > 0`)  
3) 예치량 결정  
   - 목표는 풀 현재 비율에 근접하도록 `deposit_a, deposit_b`를 결정하며, 초과 입력은 기본 “반환” 처리(명시적 donation 플래그가 없는 한).  
   - `deposit_a <= coin_a_in.amount`, `deposit_b <= coin_b_in.amount`를 만족해야 한다.  
4) 슬리피지 검증  
   - `delta = (actual_ratio_x1e18 > expected_ratio_x1e18) ? (actual_ratio_x1e18 - expected_ratio_x1e18) : (expected_ratio_x1e18 - actual_ratio_x1e18)`  
   - `delta <= floor(expected_ratio_x1e18 * max_slippage_bps / 10_000)` 만족해야 함  
   - 불만족 시 전체 실패(부분 예치 금지)

2633.3.3 단계 C — LP Units 산출 및 잠금분 처리  
- `pool.locked_lp_units`는 “영구 잠금된 LP units”이며 다음을 만족해야 한다.  
  - `pool.total_lp_units >= pool.locked_lp_units`  
  - `pool.locked_lp_units`는 외부 계정에 귀속되지 않으며, 어떠한 Remove에서도 소각될 수 없다.  
- 초기 유동성 또는 후속 유동성에 따라 다음을 사용한다.  
  - 초기:  
    - `initial_lp_units_raw = floor_sqrt(deposit_a * deposit_b)`  
    - `minted_lp_units = initial_lp_units_raw - minimum_locked_liquidity`  
    - `pool.locked_lp_units += minimum_locked_liquidity`  
  - 후속:  
    `minted_lp_units = min( deposit_a * pool.total_lp_units / pool.reserve_a, deposit_b * pool.total_lp_units / pool.reserve_b )`  
- `minted_lp_units > 0`이어야 함  
- `minimum_locked_liquidity`는 풀 완전고갈 및 회계오류 방지를 위해 풀 단위에서 잠금하며, 값 및 초기 설정 규칙은 풀 정책으로 고정되어야 한다([REFERENCE_REQUIRED]).

2633.3.4 단계 D — 원자적 상태 갱신(Atomic Commit)  
1) `pool.reserve_a += deposit_a`, `pool.reserve_b += deposit_b`  
2) `pool.total_lp_units += minted_lp_units`  
3) Position 처리  
   - 신규: `LiquidityPosition` 생성, `lp_units = minted_lp_units`  
   - 기존: `lp_units += minted_lp_units`  
   - `deposited_a += deposit_a`, `deposited_b += deposit_b`  
   - 수수료 체크포인트 업데이트:  
     - `fee_growth_checkpoint_* = pool.lp_fee_growth_global_*`  
4) 초과 입력분 반환: `coin_*_change`를 사용자에게 반환

2633.3.5 단계 E — Receipt/Event 기록(Audit Recording)  
- 성공 시 `LPActionReceipt` 생성(온체인 객체)  
- 표준 이벤트(최소):  
  - `LiquidityAdded { pool_id, position_id, actor_tmid_id, deposit_a, deposit_b, minted_lp_units, timestamp_ms, workflow_id }`

---

## 2634. RemoveLiquidity 트랜잭션 (State/Flow)

### 2634.1 목적

2634.1.1 사용자가 보유한 `LiquidityPosition`의 `lp_units`를 감소/소각하고, 풀 준비금에서 비례 자산을 반환하며, 미청구 LP 수수료를 결정론적으로 정산(포지션에 누적)한다.

### 2634.2 입력 (Command Inputs)

- `pool: &mut LiquidityPool<A,B>`  
- `position: &mut LiquidityPosition<A,B>`  
- `actor_tmid_id: ID`  
- `burn_lp_units: u128` (감소량; 전액 회수 시 `burn_lp_units = position.lp_units`)  
- `min_output_a: u128`, `min_output_b: u128` (슬리피지/최소수령)  
- `deadline_ms: u64`  
- `idempotency_key: vector<u8>`  
- `workflow_id: vector<u8>`

### 2634.3 상태/흐름 (State/Flow)

2634.3.1 단계 A — 사전검증  
1) `pool.status == ACTIVE` 또는 정책상 회수 허용 상태인지 확인(PAUSED에서 회수만 허용 등은 [REFERENCE_REQUIRED])  
2) `position.owner_tmid_id == actor_tmid_id` 확인  
3) `position.status == LOCKED`이면 실패(담보/동결/비상)  
4) `position.status == CLOSED`이면 실패  
5) `0 < burn_lp_units <= position.lp_units` 확인  
6) `now_ms <= deadline_ms` 확인  
7) 잠금분 보호 검증  
   - `pool.total_lp_units > pool.locked_lp_units` 이어야 함(회수 가능 공급 존재)  
   - `pool.total_lp_units - burn_lp_units >= pool.locked_lp_units` 이어야 함(회수로 잠금분 침범 금지)

2634.3.2 Pending Fee 정산(결정론, LP Fee 전용)  
1) 규범: 본 단계의 Fee는 `lp_fee_growth_global_*`에서 파생되는 “LP Fee”에 한정된다. Protocol Fee/기타 수익은 본 단계에서 계산·이동·혼입될 수 없다.  
2) `pending_fee_a, pending_fee_b` 계산:  
   - `pending_fee_* = f(pool.lp_fee_growth_global_*, position.fee_growth_checkpoint_*, position.lp_units)`  
   - 계산 함수 `f`는 정수 산술(예: Q128.128 등 고정 스케일)로 정의되어야 하며, 모든 나눗셈은 `floor`, 오버플로는 Abort이다([REFERENCE_REQUIRED]).  
3) `position.unclaimed_fee_* += pending_fee_*`  
4) `position.fee_growth_checkpoint_* = pool.lp_fee_growth_global_*`

2634.3.3 반환 준비금 산출(잠금분 포함 규칙)  
1) 분모는 전체 LP 공급(`pool.total_lp_units`)을 사용하되, 2634.3.1의 “잠금분 보호 검증”으로 잠금분이 회수에 의해 침범되지 않음을 보장한다.  
2) 출력량 계산:  
   - `output_a = burn_lp_units * pool.reserve_a / pool.total_lp_units`  
   - `output_b = burn_lp_units * pool.reserve_b / pool.total_lp_units`  
3) 최소수령 검증:  
   - `output_a >= min_output_a` AND `output_b >= min_output_b`  
   - 불만족 시 전체 실패(부분 반환 금지)

2634.3.4 단계 D — 원자적 상태 갱신(Atomic Commit)  
1) `pool.reserve_a -= output_a`, `pool.reserve_b -= output_b`  
2) `pool.total_lp_units -= burn_lp_units`  
3) `position.lp_units -= burn_lp_units`  
4) `position.updated_at_ms` 갱신, `generation += 1`  
5) `position.lp_units == 0`이면:  
   - `position.status = CLOSED`  
   - “Closed 재활성화 불가” 불변 적용  
6) 사용자에게 `Coin<A>(output_a)`, `Coin<B>(output_b)` 반환

2634.3.5 단계 E — Receipt/Event 기록(Audit Recording)  
- 성공 시 `LPActionReceipt` 생성(온체인 객체)  
- 표준 이벤트(최소):  
  - `LiquidityRemoved { pool_id, position_id, actor_tmid_id, output_a, output_b, burn_lp_units, timestamp_ms, workflow_id }`

---

## 2635. LP 포지션 상태기계 (State Machine)

### 2635.1 상태 전이 규칙 (Rule)

2635.1.1 허용 전이(최소):  
- `ACTIVE -> LOCKED` : 담보 예치/규제/비상정책에 의해 제한  
- `LOCKED -> ACTIVE` : 담보 해제/동결 해제/정책 종료  
- `ACTIVE -> CLOSED` : `lp_units`가 0이 되는 Remove 완료

2635.1.2 금지 전이(최소):  
- `CLOSED -> *` 전이 전면 금지  
- `LOCKED` 상태에서 `RemoveLiquidity` 실행 금지  
- 임의 상태값 변경 함수 호출 금지(전용 전이 함수만 허용)

### 2635.2 검증/권한 (Validation/Authorization)

- `ACTIVE`에서 Remove 실행 시: Ownership + Financial + Object + Liquidity Authorization 필요  
- `LOCKED` 해제 전이 시: DAO/Treasury Policy 또는 Emergency Authorization이 추가로 필요([REFERENCE_REQUIRED])

### 2635.3 실패 처리 (Failure Handling)

- 상태 부적합 시 `E1008 Invalid Object State` 또는 `E1007 Business Rule Violation`로 실패  
- 실패 시 pool/position/coin 변경은 전부 롤백(원자성)

---

## 2636. 준비금 기반 제약 (Reserve-backed Constraints)

### 2636.1 목적

2636.1.1 유동성 생성이 준비금·소유권·상환 경로를 우회하여 “무담보 경제 상태”를 만들지 못하도록 제한한다.

### 2636.2 규칙 (Rule)

2636.2.1 범위 한정 규칙(FT-FT Add/Remove 전용)  
- 본 절(2631~2640)은 FT-FT 풀의 Add/Remove만을 다룬다. Gold NFT가 포함되는 Hybrid NFT·FT Pool의 예치/회수 및 Exit(FT-only Exit, Pro-rata FT·NFT Exit 등)는 별도 절에서 정의한다([REFERENCE_REQUIRED]).  
- 따라서 본 절의 FT-FT 풀 경로에서는 Gold NFT를 직접 입력 자산으로 수용하지 않는다(“혼합 금지”).

2636.2.2 `GOLDPEG`의 유동성 공급(AddLiquidity)은 이미 발행된 `GOLDPEG`만을 사용하며, AddLiquidity가 새로운 발행(Mint)이나 준비금 할당(Reserve Allocation)을 직접 유발해서는 안 된다.  
- 규범: 본 절의 LP Add/Remove는 발행/할당 트랜잭션을 호출하지 않는다. 인센티브/보조금은 별도 모듈의 “명시적 Reward Claim”로만 발생한다([REFERENCE_REQUIRED]).

2636.2.3 Add/Remove는 상환 상태(Pending/Final) 또는 준비금 상태(Reserved/Released/Frozen)를 변경하지 않는다.  
- 상환/준비금 변경은 별도 트랜잭션 및 별도 권한(Reserve Authorization)으로만 수행한다.

### 2636.3 검증 (Validation)

- 입력 자산이 `GOLDPEG` 또는 허용된 Pair Asset인지 확인  
- FT-FT 풀 경로에서 NFT 타입/객체가 입력되는 경우 즉시 실패

### 2636.4 감사 (Audit)

- 성공 Receipt 또는 실패 Event에 입력 자산 타입, allowlist 판정 결과, oracle/circuit 상태 요약을 포함해야 한다.

---

## 2637. 정산/수수료 누적(Accounting) 모델 및 감사 이벤트

### 2637.1 목적

2637.1.1 Swap 등 풀 활동으로 발생한 “LP Fee”를 전역 누적치(Global Fee Growth)로 기록하고, 각 포지션별 체크포인트 방식으로 결정론적으로 배분한다.

### 2637.2 규칙 (Rule)

2637.2.1 수수료 누적:  
- Swap 발생 시 `pool.lp_fee_growth_global_a/b`가 증가한다(증가 로직은 Swap 절에서 정의).  
- 포지션은 Add/Remove 시점에 `fee_growth_checkpoint_*`를 갱신하여 이후 발생분만 청구 가능하도록 한다.

2637.2.2 분리회계 규범(혼입 금지):  
- `lp_fee_growth_global_*` 및 `position.unclaimed_fee_*`는 사용자 귀속 “LP Fee”에 한정된다.  
- Protocol Fee/Marketplace Fee/Insurance Allocation/기타 수익은 별도 누적치 및 별도 금고/분배 프레임워크에서 처리되어야 하며, 본 절의 Fee 정산 경로에 포함될 수 없다.

### 2637.3 이벤트 (Events)

- `FeeGrowthUpdated { pool_id, lp_fee_growth_global_a, lp_fee_growth_global_b, timestamp_ms }` (Swap 모듈이 발행)  
- `PositionFeeCheckpointed { position_id, checkpoint_a, checkpoint_b, timestamp_ms }`  
- `LPActionReceiptCreated { receipt_id, action_type, pool_id, position_id_opt, actor_tmid_id, result_code }`  
- `LPActionFailed { action_type, pool_id, position_id_opt, actor_tmid_id, error_code, timestamp_ms, workflow_id, idempotency_key }` (Abort 기록용)

### 2637.4 감사 레코드 (Audit Record)

- 모든 LP 액션은 `workflow_id`로 연결되어야 하며, 동일 `idempotency_key` 재호출 시 동일 결과 또는 “이미 처리됨”으로 귀결되어야 한다.  
- Receipt의 `pre_state_hash/post_state_hash`는 최소 `pool.reserve_*`, `pool.total_lp_units`, `pool.locked_lp_units`, `position.lp_units`, `fee_growth_checkpoint_*`를 포함하는 정규화 해시여야 한다([REFERENCE_REQUIRED]).

---

## 2638. 실패 처리: 부분 실패 금지/원자성 보장

### 2638.1 원칙 (Rule)

2638.1.1 AddLiquidity/RemoveLiquidity는 다음 중 하나로만 종료된다.  
- (A) 모든 검증 통과 + 모든 자산 이동/상태 갱신 + Receipt 기록(Audit Recording)까지 완료된 성공  
- (B) 어떠한 상태/자산 변화도 남기지 않는 실패(Abort) + 실패 이벤트 `LPActionFailed` 기록(인덱싱 포함)

2638.1.2 부분 예치(한쪽 자산만 예치), 부분 회수(최소수령 미달에서 일부만 지급), 부분 Fee 정산 후 실패 등의 중간 상태를 금지한다.

### 2638.2 실패 코드 (Failure Handling)

- `E1007 Business Rule Violation`: 슬리피지 초과, 최소수량 미달, 비율 불일치 등  
- `E1008 Invalid Object State`: pool not ACTIVE, position LOCKED/CLOSED 등  
- `E1002 Unauthorized Caller`: 소유권 불일치  
- `E1009 Authorization Expired`: deadline 초과 또는 authorization 만료  
- `E1010 Replay Attack Detected`: idempotency 충돌/재사용 규칙 위반

### 2638.3 실패 시 처리

- Sui 트랜잭션 Abort로 pool/position/coin 변경은 전부 롤백  
- 실패 기록은 온체인 객체(Receipt)가 아니라 표준 실패 이벤트 `LPActionFailed`로만 수행한다(원자성 불변과의 충돌 제거).

---

## 2639. 감사(Audit)

### 2639.1 목적

2639.1.1 LP 관련 모든 상태변경 및 회계 변화는 사후 재현 가능해야 하며, 외부 감사자가 풀 준비금/LP 공급량/포지션 지분/수수료 배분을 결정론적으로 검산할 수 있어야 한다.

### 2639.2 감사 요구사항 (Audit Requirements)

- 각 트랜잭션은 `workflow_id`로 연결  
- Add/Remove는 `LiquidityAdded/LiquidityRemoved` 이벤트를 반드시 남김  
- 성공 시 Receipt에는 다음을 포함:  
  - 입력/출력 수량, 최소수령/슬리피지 파라미터  
  - pool/position 상태 요약 해시  
  - EAF 결과 digest(누가 어떤 권한으로 실행했는지)  
- 실패 시 이벤트에는 다음을 포함:  
  - `error_code`, `workflow_id`, `idempotency_key`, `pool_id`, `position_id_opt`, `actor_tmid_id`

### 2639.3 분리회계 검증

- 사용자 자산(풀 reserve, 미청구 LP fee)과 Treasury/Protocol Revenue/Insurance Reserve는 단일 트랜잭션에서 혼합 정산되지 않아야 한다.  
- 프로토콜이 LP 보조금/인센티브를 제공하는 경우에도 본 절의 Add/Remove에는 포함되지 않으며, 별도 Reward Claim 트랜잭션에서만 발생하고 출처(Value Source)가 명시되어야 한다([REFERENCE_REQUIRED]).

---

## 2640. 불변식(Invariants)

2640.1 **원자성 불변식(Atomicity Invariant)**  
- Add/Remove는 부분 성공 상태를 남기지 않는다.

2640.2 **LP 공급-준비금 정합 불변식(Accounting Consistency)**  
- `pool.total_lp_units` 증감은 오직 Add/Remove에서만 발생한다.  
- Add에서 `reserve_a/reserve_b` 증가는 `deposit_a/deposit_b`와 일치해야 한다.  
- Remove에서 `reserve_a/reserve_b` 감소는 `output_a/output_b`와 일치해야 한다.

2640.3 **잠금 유동성 보존 불변식(Locked Liquidity Preservation)**  
- 항상 `pool.total_lp_units >= pool.locked_lp_units`가 성립해야 한다.  
- 어떠한 Remove도 `pool.locked_lp_units`를 침범할 수 없다(2634.3.1의 검증으로 강제).

2640.4 **포지션 폐쇄 불변식(Closed Position Invariant)**  
- `position.status == CLOSED`이면 `position.lp_units == 0`이며, 어떠한 방법으로도 ACTIVE/LOCKED로 전이될 수 없다.

2640.5 **LOCKED 회수 금지 불변식(Locked Withdrawal Prohibition)**  
- `position.status == LOCKED`인 동안 RemoveLiquidity는 실패해야 한다.

2640.6 **결정론적 수수료 불변식(Deterministic Fee Accrual)**  
- 동일한 `pool.lp_fee_growth_global_*` 및 `position` 상태에서 `pending_fee_*` 계산 결과는 노드/환경에 무관하게 동일해야 한다.

2640.7 **준비금/상환 우회 금지 불변식(Reserve/Redemption Non-bypass)**  
- LP Add/Remove는 준비금 객체, 상환 객체, 원금 소유권 NFT 상태를 변경하지 않으며, 이를 우회하는 방식으로 준비금 기반 제약을 약화시키지 않는다.

2640.8 **자산 혼합 금지 불변식(No NFT-in-FT-FT-AMM Mixing)**  
- 본 절의 FT-FT 풀 Add/Remove 경로에서는 Gold NFT를 직접 입력 자산으로 수용하지 않는다(Hybrid NFT·FT Pool은 별도 절).

---
```

<-bash: cd: /home/boshin57/tobmate-agent-factory: No such file or SOURCE: workspace/drafts/3O_2641_2650_approved.md -->
```markdown
## 2641. 스왑 엔진(Swap Engine) 개요

### 2641.1 Purpose
GLPF의 스왑 엔진(Swap Engine)은 GOLDPEG 및 허용된 상대 자산 간 교환을 **결정론적(deterministic)** 이고 **원자적(atomic)** 으로 실행하며, 모든 실행이 **Constitution 상위 검증**, **BRVF(Business Rule Validation Framework)**, **EAF(Execution Authorization Framework)** 를 통과하도록 표준화한다.

### 2641.2 Architecture or Rule
- 모든 스왑은 다음의 **헌법 우선 파이프라인**을 따른다(동일 트랜잭션 내).
  - **Move Entry → Constitution/Static Invariant Check → BRVF 검증(What) → EAF 승인(Who) → Atomic Execution → Audit Record → Commit**
- 스왑 엔진은 풀 유형별(예: Constant Product, Concentrated Liquidity, Oracle-guided Curve) **가격 함수(Price Function)** 를 호출하되, 스왑 결과는 반드시 해당 풀의 **풀 불변식(Pool Invariants)** 을 만족해야 한다.
- 다중 경로(route) 스왑은 단일 트랜잭션 내에서 **연쇄 원자 실행(atomic chaining)** 으로 처리하며, 어느 한 홉(hop)이라도 실패하면 전체가 Abort된다(All-or-Nothing).

### 2641.3 State/Flow
- 입력: `SwapRequest`
- 처리:
  1. Constitution/Static Invariant Check: 금지된 상태 전이, 필수 감사 기록 요건 등 상위 불변식 사전 검증
  2. BRVF: 라우트 규칙, 슬리피지, 한도, 가격 보호(Oracle Guard), 서킷 브레이커(Circuit Breaker), 수학 불변식 검증
  3. EAF: 호출자 권한, 객체 변경 권한, 자산 권한, 정책 유효성(버전 포함), (적용 시) 리플레이 방지 상태 확인
  4. Lock: 관련 Pool/Vault/Policy/Guard/CircuitBreaker/ReplayProtection Object를 **object_id 바이트 오름차순**으로 정렬하여 잠금  
     - route 내 동일 객체가 중복 참조되는 경우, 중복 잠금을 금지하고 **단일 락**으로 통합한다.
  5. 실행: 수수료·출력량 계산, 잔고 업데이트, 표준 이벤트/감사 기록(2650)
  6. Commit 후 Unlock
- 출력: `SwapResult`

### 2641.4 Validation
- Constitution/BRVF/EAF 중 어느 하나라도 실패 시 **상태 변경 없이 즉시 Abort**.
- 모든 수치 연산은 고정 정밀도(fixed precision) 및 **결정론적 라운딩 규칙(2644.2.3)** 을 적용한다.

### 2641.5 Failure handling
- `E1002 Unauthorized Caller`, `E1007 Business Rule Violation`, `E1008 Invalid Object State`를 기본 매핑으로 사용한다.
- Lock 획득 실패 또는 동시성 충돌은 트랜잭션 Abort로 처리하며 부분 실행(partial execution)을 금지한다.

### 2641.6 Audit
- 표준 이벤트(Event)·감사(Audit) 규격은 **2650**에서 정의한다.
- 스왑 엔진은 성공 시 `SwapExecutedEvent` 및 필수 감사 레코드를 동일 트랜잭션 digest에 귀속시켜 기록해야 한다.

### 2641.7 Invariants
- 원자성: 다중 홉 포함 전체 성공 또는 전체 실패.
- 결정론: 동일 입력은 동일 출력(라운딩 포함)을 산출.
- 불변식: 풀 불변식 및 잔고 보존(2648)을 위반하는 Commit은 금지.
- 감사: “감사 기록(Audit Recorded)”이 누락된 Commit은 금지.


## 2642. 스왑 트랜잭션 모델(exact-in / exact-out) 및 라우트(route) 규칙

### 2642.1 Purpose
사용자/프로토콜이 요청하는 스왑을 표준 입력 모델로 정규화하여, BRVF 검증 및 감사 추적을 일관되게 수행한다.

### 2642.2 Architecture or Rule
#### 2642.2.1 SwapRequest (Object Model)
```move
public struct SwapRequest has copy, drop {
  request_id: vector<u8>,                 // caller-supplied nonce (anti-replay scope)
  mode: u8,                               // 0=EXACT_IN, 1=EXACT_OUT
  route: vector<RouteHop>,                // ordered hops
  amount_specified: u64,                  // exact_in input OR exact_out output
  limit_amount: u64,                      // min_out (exact_in) OR max_in (exact_out)
  recipient: address,                     // output recipient
  deadline_ms: u64,                       // expiry
  slippage_ppm: u64,                      // user tolerance (ppm)
  client_tag: vector<u8>,                 // optional audit tag
}
public struct RouteHop has copy, drop {
  pool_id: ID,
  token_in: TypeTag,
  token_out: TypeTag,
  curve_type: u8,                         // pool curve selector (must match pool)
}
```
- `TypeTag`는 감사/재현을 위해 **체인 표준 정규 직렬화(canonical serialization)** 형태로만 기록·해석되어야 한다(텍스트 표현 의존 금지).

#### 2642.2.2 SwapResult (Output Model)
```move
public struct SwapResult has copy, drop {
  request_id: vector<u8>,
  mode: u8,
  amount_in: u64,
  amount_out: u64,
  total_fee_amount: u64,
  fee_breakdown: vector<FeeLine>,
  route_receipts: vector<HopReceipt>,
}
public struct HopReceipt has copy, drop {
  pool_id: ID,
  token_in: TypeTag,
  token_out: TypeTag,
  amount_in: u64,
  amount_out: u64,
  fee_amount: u64,
  price_before_x64: u128,                 // fixed-point snapshot (implementation-defined)
  price_after_x64: u128,
}
public struct FeeLine has copy, drop {
  category: u8,                           // LP/Protocol/Treasury/Insurance/DAO 등
  amount: u64,
  receiver: ID,                           // Treasury/Insurance/DAO object id, or pool fee vault id
}
```

### 2642.3 State/Flow
- EXACT_IN:
  - `amount_specified`를 입력으로 고정하고, 산출 `amount_out`이 `limit_amount(min_out)` 이상이어야 한다.
- EXACT_OUT:
  - `amount_specified`를 출력으로 고정하고, 필요 `amount_in`이 `limit_amount(max_in)` 이하여야 한다.
- 라우트는 `route[0]..route[n-1]` 순서대로 실행되며 각 홉의 출력이 다음 홉의 입력이 된다.

### 2642.4 Validation
- `deadline_ms < now_ms` 이면 `E1009 Authorization Expired`로 Abort.
- `route.len == 0` 또는 hop 토큰 불일치 시 `E1007`.
- 각 hop에 대해:
  - 풀의 등록된 자산 쌍 및 `curve_type` 일치 검증
  - 풀 상태가 ACTIVE가 아니면 `E1008`
- EXACT_IN/OUT 한도 조건 위반 시 `E1007`.

### 2642.5 Failure handling
- 경로 중간 실패 시 이미 계산된 중간 값도 Commit되지 않으며 전부 Abort.
- 리플레이 방지(anti-replay)가 활성화된 정책에서 동일 `request_id` 재사용이 탐지되면 `E1010 Replay Attack Detected`로 Abort(구체 상태 모델은 2649.2.2).

### 2642.6 Audit
- `SwapRequest`의 원문 핵심 필드(해시)와 `route_receipts`를 이벤트에 기록한다.
- `client_tag`는 감사/분쟁 대응용으로 원문 그대로 기록 가능하나, 프로토콜 의미론에 영향을 주지 않아야 한다.

### 2642.7 Invariants
- 라우트 실행 순서는 입력 벡터 순서를 그대로 따른다(재정렬 금지).
- EXACT_IN의 최소수령(min_out), EXACT_OUT의 최대지급(max_in)은 모든 홉 실행 종료 후 최종값으로 단 한 번 검증한다(중간 홉 부분 검증은 선택적으로 추가 가능하나 결과를 변경해서는 안 됨).


## 2643. 가격 함수(Price Function) 선언 및 풀 불변식(Pool Invariants) 호출 규약

### 2643.1 Purpose
풀 유형별 수학 모델을 “선언적으로” 호출 가능하게 하여 BRVF가 불변식 검증을 일관되게 수행하도록 한다.

### 2643.2 Architecture or Rule
#### 2643.2.1 PoolCore (공통 필드)
```move
public struct PoolCore has key {
  id: UID,
  token_x: TypeTag,
  token_y: TypeTag,
  vault_x: ID,                            // balance object id
  vault_y: ID,
  curve_type: u8,                         // 0=CPMM, 1=CLMM, 2=ORACLE_CURVE ...
  status: u8,                             // ACTIVE/FROZEN/...
  fee_policy_id: ID,
  oracle_guard_id: option::Option<ID>,
  circuit_breaker_id: option::Option<ID>,
  version: u64,
  updated_at_ms: u64,
}
```

#### 2643.2.2 PriceFunctionHook (BRVF 검증 훅)
- 스왑 실행 전/후에 BRVF는 다음 훅을 호출(논리적 호출; 구현은 모듈 인터페이스로 구체화):
  - `quote_exact_in(pool, token_in, amount_in) -> (amount_out, fee)`
  - `quote_exact_out(pool, token_out, amount_out) -> (amount_in, fee)`
  - `validate_invariant_before(pool_snapshot)`
  - `validate_invariant_after(pool_snapshot_before, pool_snapshot_after)`

### 2643.3 State/Flow
- 엔진은 각 hop에 대해:
  1. `pool_snapshot_before` 생성(금고 잔고, 가격 상태, 정책 버전 등)
  2. quote 함수로 산출값 계산(라운딩은 2644.2.3 준수)
  3. BRVF 불변식/가드 검증(2646~2648)
  4. 금고 잔고 업데이트
  5. `pool_snapshot_after` 생성 및 불변식 재검증

### 2643.4 Validation
- `curve_type` 미지원이면 `E1007`.
- `token_in/token_out`이 풀의 `(token_x, token_y)`와 일치하지 않으면 `E1007`.
- `validate_invariant_*` 실패 시 `E1007`.

### 2643.5 Failure handling
- quote/검증 단계에서의 산술 오버플로우/언더플로우는 `E1007`로 Abort(부분 업데이트 금지).

### 2643.6 Audit
- `curve_type`, `fee_policy_id`, `oracle_guard_id`, `circuit_breaker_id`, `version`을 HopReceipt에 기록하여 사후 재현 가능성을 보장한다.

### 2643.7 Invariants
- 불변식 검증은 **Commit 이전**에 반드시 성공해야 하며, 실패 상태는 Consensus에 의해 승인될 수 없다(Constitution 상위 원칙 준수).


## 2644. 수수료 계산, 라운딩, 결정론적 정렬(Sort) 규칙

### 2644.1 Purpose
수수료(Fee) 및 출력량 계산에서의 비결정성을 제거하고, 잔여(dust) 발생 및 이중 청구를 방지한다.

### 2644.2 Architecture or Rule
#### 2644.2.1 FeePolicy (Object Model)
```move
public struct FeePolicy has key {
  id: UID,
  policy_version: u64,
  base_fee_ppm: u64,                      // e.g., 2500 = 0.25%
  fee_cap_ppm: u64,
  dynamic_fee_enabled: bool,
  receivers: vector<FeeReceiver>,         // deterministic order required
  rounding_mode: u8,                      // 0=FLOOR, 1=CEIL (default=FLOOR)
  updated_at_ms: u64,
}
public struct FeeReceiver has copy, drop {
  category: u8,                           // LP/Protocol/Treasury/Insurance/DAO...
  share_ppm: u64,                         // sum must equal 1_000_000
  receiver_id: ID,
}
```

#### 2644.2.2 결정론적 정렬 규칙
- `receivers`는 (1) `category` 오름차순, (2) `receiver_id` 바이트 오름차순으로 정렬된 상태로만 저장/업데이트 가능.
- 스왑 엔진은 `FeeReceiver`를 재정렬하지 않고 저장된 순서 그대로 적용한다.
- 정렬 규칙 위반이 검출되면 `E1007 Business Rule Violation`로 Abort한다.

#### 2644.2.3 라운딩 규칙
- 기본 라운딩은 `FLOOR`(내림)로 고정한다.
- 분배 라운딩:
  - 각 수신자 금액 = `floor(total_fee * share_ppm / 1_000_000)`
  - 마지막 수신자(정렬 기준 최후 항목)에 `remainder = total_fee - sum(others)`를 가산하여 **잔여 금액 0**을 강제한다.
- 금액 산출 라운딩(quote)은 풀 수학모델별로 정의하되, 동일 입력에 대해 동일 결과를 강제해야 한다.

#### 2644.2.4 동적 수수료(Dynamic Fee) 결정론 제약
- `dynamic_fee_enabled=true`인 경우에도, 동적 가산치 산출은 **결정론적 입력**(예: 오라클 편차, 정책에 정의된 정규화된 변동성 지표 등)만을 사용해야 하며, `fee_cap_ppm`을 초과할 수 없다.
- 동적 가산치 산출식 및 입력 지표의 정확한 정의는 [REFERENCE_REQUIRED]로 둔다.

### 2644.3 State/Flow
- `total_fee_amount`는 hop별 fee를 합산하여 산출한다.
- 분배는 hop 단위 또는 전체 스왑 단위 중 정책으로 선택하되(풀 설정), 어느 방식이든 **총 Fee = 분배 합**을 만족해야 한다.

### 2644.4 Validation
- `sum(receivers.share_ppm) == 1_000_000` 미만/초과는 `E1007`.
- `base_fee_ppm <= fee_cap_ppm` 위반 시 `E1007`.
- 분배 후 `sum(distribution) != total_fee_amount`이면 `E1007`.

### 2644.5 Failure handling
- 수수료 정책 누락/버전 불일치: `E1005 Policy Not Found` 또는 `E1006 Policy Version Mismatch`.
- 분배 불변식 위반은 즉시 Abort하며 Rollback 없는 부분지급을 금지한다.

### 2644.6 Audit
- `policy_version`, `base_fee_ppm`, 적용된 동적 가산치(있는 경우), 분배 내역(FeeLine)을 이벤트와 감사 레코드에 기록한다.

### 2644.7 Invariants
- 총 Fee = 모든 분배 금액의 합.
- 음수 Fee 금지.
- 중복 지급 금지.
- 동일 Fee의 이중 청구 금지.
- Distribution 완료 후 Rollback 금지(원자 실행으로 보장).


## 2645. MEV/프론트런 완화의 규칙적 경계(정책 수준 정의)

### 2645.1 Purpose
MEV 및 프론트런(front-running)을 “완전 차단”이 아닌 **정책적 경계(policy boundary)** 로 정의하여, 결정론 및 감사 가능성을 유지하면서 피해를 제한한다.

### 2645.2 Architecture or Rule
- 스왑 엔진은 다음 완화 수단을 **정책 객체(Policy Object)** 로 구성 가능해야 한다.
  1. `deadline_ms` 강제(만료 거래 무효)
  2. 슬리피지 한도(`slippage_ppm` + `limit_amount`) 강제
  3. Oracle Price Guard(2647) 강제
  4. Circuit Breaker 상태(LEVEL)에 따른 거래 제한(2647)
  5. (제한 풀의 경우) 허용된 호출자/라우터만 실행 가능(2649)

### 2645.3 State/Flow
- 모든 완화는 BRVF 검증 단계에서 **거부(Reject gating)** 로만 작동하며, 실행 결과를 “수정”하지 않는다.
- 보호 정책이 활성화된 풀의 **거부 판단 우선순위(Reject gating priority)** 는 다음과 같다.  
  `CircuitBreaker > OracleGuard > Slippage/Limit > Deadline`  
  단, `FeePolicy`는 산출(quote/fee 계산)에 항상 적용되며, 거부 판단의 선후와 무관하다.

### 2645.4 Validation
- 보호 정책 위반은 `E1007`.
- 정책 객체의 상태가 FROZEN/INVALID이면 `E1008`.

### 2645.5 Failure handling
- 보호 정책 위반 시 부분 체결(partial fill) 없이 전체 Abort.

### 2645.6 Audit
- 어떤 보호 규칙이 위반되었는지 식별 가능한 `failure_reason_code`를 감사 로그에 기록해야 한다(에러코드 자체는 Table 3 의미 유지).

### 2645.7 Invariants
- MEV 완화는 가격/수량 산출의 결정론을 변경해서는 안 되며, 오직 “허용/거부”만 수행한다.


## 2646. BRVF 검증: 잔고 보존, 불변식 유지, 한도/슬리피지

### 2646.1 Purpose
스왑 실행이 경제적/수학적/정책적 제약을 만족하는지 BRVF에서 표준 방식으로 검증한다.

### 2646.2 Architecture or Rule
BRVF는 스왑에 대해 최소 다음 검증 모듈을 적용한다.
- Liquidity Rules: 풀 상태, 라우트 규칙, 유동성 존재, 가격 함수 적합성
- Treasury/Revenue Rules: 수수료 분배 무결성
- Compliance Rules(선택): 허용 자산/사용자 정책(제한 풀)
- Oracle/Guard Rules: 가격 괴리, staleness, confidence
- Circuit Breaker Rules: 레벨별 제한
- Replay Protection Rules(적용 시): `request_id` 재사용 탐지(2649.2.2)

### 2646.3 State/Flow
- 입력: `SwapRequest`, 풀/정책 스냅샷
- 출력: `BRVFApproval`(통과) 또는 에러(거부)
- 통과 후에만 EAF 및 Atomic Execution 단계로 진행한다.

### 2646.4 Validation
- 잔고 보존(2648):
  - 각 hop에서 `vault_in` 증가량과 사용자/이전 hop 감소량의 회계가 일치해야 한다.
  - `total_fee_amount`는 입력 또는 출력에서 차감되는 방식이 명시되어야 하며(풀 정책), 회계적으로 일관되어야 한다.
- 한도/슬리피지:
  - EXACT_IN: `amount_out >= min_out(limit_amount)`
  - EXACT_OUT: `amount_in <= max_in(limit_amount)`
- 정책 버전:
  - `FeePolicy.policy_version` 및 Guard/CircuitBreaker/Execution/ReplayProtection 정책 버전이 풀에 기록된 참조와 일치해야 한다. 불일치 시 `E1006`.

### 2646.5 Failure handling
- 검증 실패는 Commit 이전 Abort로 처리하며, 어떠한 객체도 변경될 수 없다.

### 2646.6 Audit
- BRVF 검증 통과 시 `SwapExecutedEvent` 또는 감사 레코드 필드로 다음을 기록:
  - 검증된 정책 ID/버전 목록
  - 적용된 제한(슬리피지, 가드 임계값, 서킷 레벨)

### 2646.7 Invariants
- BRVF는 “무엇을 실행할 수 있는가(What Can Execute)”의 최종 관문이며, 불변식 위반을 포함한 모든 비즈니스 규칙 위반은 Consensus에 상정될 수 없다.


## 2647. Oracle Price Guard 및 Circuit Breaker 연동 불변식

### 2647.1 Purpose
AMM 내부 가격만을 신뢰하지 않고 금 기준 오라클(oracle)과의 괴리 및 오라클 품질을 검증하여 조작/급변 리스크를 제한한다.

### 2647.2 Architecture or Rule
- Oracle Guard 객체는 설계 문서의 필드를 따른다(예시 구조 준수).  
  `OracleGuard` 필드: `maximum_deviation_ppm`, `maximum_staleness_ms`, `minimum_confidence_ppm`, `twap_window_ms`, `maximum_twap_deviation_ppm`, `status`, `updated_at_ms`
- Circuit Breaker는 레벨(LEVEL_0~LEVEL_3)을 가지며 레벨에 따라:
  - LEVEL_1: 거래 한도 축소
  - LEVEL_2: 동적 수수료 상향(단, Fee Cap 준수; 동적 산출은 2644.2.4의 결정론 제약을 따른다)
  - LEVEL_3: 대규모 swap 정지 또는 특정 모드(EXACT_OUT 등) 금지
- Oracle Guard 및 Circuit Breaker의 구체 정책 임계값은 풀별 정책 객체로 외부화한다.

### 2647.3 State/Flow
- 각 hop 실행 전:
  1. 오라클 가격 및 최신성(staleness) 확인
  2. 풀 현물가격(spot) 및 TWAP(필요 시) 산출
  3. `abs(pool_price - oracle_price)/oracle_price <= maximum_deviation_ppm` 검증
  4. Circuit Breaker 레벨 판정 및 제한 적용

### 2647.4 Validation
- 오라클 stale: `now_ms - oracle.updated_at_ms > maximum_staleness_ms`이면 `E1007`.
- confidence 미달 또는 TWAP 괴리 초과도 `E1007`.
- Circuit Breaker 레벨이 거래를 금지하면 `E1007`.

### 2647.5 Failure handling
- Guard 실패는 거래 거부(Abort)로만 처리하며, 자동 보정(repricing) 또는 부분 체결을 금지한다.

### 2647.6 Audit
- 이벤트에 다음을 기록:
  - oracle_feed_id, 관측 oracle_price, pool_price, deviation_ppm
  - twap 사용 시 twap_price, twap_deviation_ppm
  - circuit_breaker_level

### 2647.7 Invariants
- Oracle Guard가 설정된 풀은 Guard 검증 없는 swap Commit이 불가하다.
- Circuit Breaker가 LEVEL_3인 경우 정책이 허용한 범위를 초과하는 거래는 반드시 거부되어야 한다.


## 2648. AMM 불변식(AMM Invariants) 및 잔고 보존(Conservation) 규칙

### 2648.1 Purpose
스왑 실행으로 인해 풀의 수학적 불변식이 깨지거나, 자산이 “생성/소멸”되는 회계 불일치가 발생하지 않도록 한다.

### 2648.2 Architecture or Rule
- 풀 유형별 핵심 불변식은 `PriceFunctionHook`의 `validate_invariant_before/after`가 규정한 **규범적 형태**를 사용한다(2643.2.2).
- 다음 수식은 비규범적 예시이며, 구현 검증은 훅 정의를 우선한다.
  - Constant Product(CPMM) 예시: 수수료/라운딩/정의역을 반영한 형태의 `k` 불변식(구체형은 풀 모듈에 의해 정의)
- 스왑은 항상 다음 “보존”을 만족해야 한다.
  - 입력 토큰: 사용자(또는 이전 hop)의 감소량 = 풀 금고 증가량 + fee 분배로 이동된 총량(정책에 따라)
  - 출력 토큰: 풀 금고 감소량 = 사용자(또는 다음 hop)의 증가량

### 2648.3 State/Flow
- 각 hop에서 `before(x,y,curve_state)` → 계산/분배 → `after(x',y',curve_state')`
- BRVF는 before/after 스냅샷으로 불변식을 검증한다.

### 2648.4 Validation
- 음수 잔고/언더플로우 금지(검출 시 `E1007`).
- 불변식 검증 실패 시 `E1007`.
- fee 분배 합 불일치 시 `E1007`.

### 2648.5 Failure handling
- 어떤 불변식 실패도 예외 없이 Abort한다.
- 실패한 트랜잭션이 이벤트를 남기는 경우, “실패 이벤트”는 상태 변경을 포함하지 않는 감사용 기록으로만 제한되어야 한다(성공 이벤트와 구분).

### 2648.6 Audit
- HopReceipt에 `amount_in/amount_out/fee_amount` 및 `price_before/after`를 기록하여 불변식 재검증을 가능하게 한다.

### 2648.7 Invariants
- 스왑 Commit 이후 풀 금고 잔고는 항상 0 이상이며, 풀 상태(status)가 ACTIVE인 동안 정의된 불변식을 유지한다.
- 총 Fee 및 분배 불변식은 2644.7을 동일 의미로 준수한다.


## 2649. EAF 승인: 공개/제한 스왑 및 역할 기반 제어(RBAC)

### 2649.1 Purpose
“누가 swap을 실행할 수 있는가(Who Can Execute)”를 EAF 정책으로 강제하여, 퍼블릭 풀과 제한 풀의 실행 권한을 동일 프레임워크에서 통제한다.

### 2649.2 Architecture or Rule
- Authorization Category 매핑(표준 의미 유지):
  - Identity Authorization: TMID 기반 호출자 인증(적용 시)
  - Object Authorization: PoolCore/FeePolicy/Guard/CircuitBreaker/ReplayProtection 등 **정책·상태 객체 참조의 정합성** 및 엔트리 실행 권한 경로 검증
  - Financial Authorization: 입력 토큰(FT/GOLDPEG) 이동 권한(서명/소유권/승인 모델)
  - Treasury Authorization: Protocol fee가 Treasury로 이동하는 경우 해당 정책에 따른 승인
  - Regulatory Authorization: 제한 풀의 규제 정책 검증(적용 시)
  - Emergency Authorization: 비상 특례 실행 및 FROZEN 해제 등(스왑 일반 경로에는 기본적으로 포함되지 않음)
- 스왑은 LP 포지션 권리와 분리되어야 하며, **Liquidity Authorization은 LP 포지션 변경(유동성 추가/제거/수수료 청구)** 에 한정한다.  
  스왑에서 발생하는 풀 금고 업데이트는 스왑 모듈의 Object Authorization 경로로 수행되며, LP 개별 권한을 요구해서는 안 된다(최소권한).

#### 2649.2.1 SwapExecutionPolicy (Object Model)
```move
public struct SwapExecutionPolicy has key {
  id: UID,
  policy_version: u64,
  access_mode: u8,                        // 0=PUBLIC, 1=ALLOWLISTED, 2=ROUTER_ONLY
  allowlist: vector<address>,             // sorted ascending
  approved_routers: vector<address>,      // sorted ascending
  require_tmid: bool,
  require_compliance_check: bool,
  replay_protection_id: option::Option<ID>,
  updated_at_ms: u64,
}
```

#### 2649.2.2 ReplayProtectionPolicy (Object Model)
- 리플레이 방지(anti-replay)는 선택 정책으로 제공하되, 활성화된 경우에는 온체인 상태로 **결정론적으로** 탐지되어야 한다.
```move
public struct ReplayProtectionPolicy has key {
  id: UID,
  policy_version: u64,
  mode: u8,                               // 0=OFF, 1=NONCE_TABLE, 2=MONOTONIC
  scope_mode: u8,                         // 0=CALLER, 1=(CALLER,EXEC_POLICY), 2=(CALLER,POOL)
  updated_at_ms: u64,
}
public struct NonceStore has key {
  id: UID,
  scope_hash: vector<u8>,                 // hash(scope tuple), canonical
  used: table::Table<vector<u8>, bool>,   // request_id -> used
  updated_at_ms: u64,
}
public struct MonotonicNonce has key {
  id: UID,
  scope_hash: vector<u8>,
  last_nonce: u128,                       // caller must supply strictly increasing nonce encoding
  updated_at_ms: u64,
}
```
- `scope_hash`는 scope tuple을 canonical serialization로 인코딩 후 해시한 값이어야 한다.

### 2649.3 State/Flow
- PUBLIC: 누구나 호출 가능하되, 자산 이동 권한 및 객체 변경 권한은 트랜잭션 서명/소유권으로 충족되어야 한다.
- ALLOWLISTED: 호출자가 allowlist에 존재해야 한다.
- ROUTER_ONLY: 승인된 router만 엔트리 호출 가능(사용자는 router에 위임/서명 모델로 참여).
- ReplayProtection이 활성화된 경우:
  - NONCE_TABLE: `request_id`가 `NonceStore.used`에 존재하면 거부, 성공 Commit 시 `used[request_id]=true`로 기록
  - MONOTONIC: 제출 nonce가 `last_nonce`보다 크지 않으면 거부, 성공 Commit 시 `last_nonce` 갱신

### 2649.4 Validation
- `require_tmid=true`인 경우 TMID 검증 실패는 `E1001 Invalid TMID`.
- allowlist/router 미일치: `E1002 Unauthorized Caller`.
- policy_version 불일치(풀 참조 버전 != 정책 버전): `E1006 Policy Version Mismatch`.
- 권한(capability) 누락/무효: `E1003 Invalid Capability` 또는 `E1004 Permission Denied`.
- ReplayProtection 위반: `E1010 Replay Attack Detected`.

### 2649.5 Failure handling
- EAF 승인 실패는 상태 변경 없이 Abort.
- 만료/재사용 탐지 시 `E1009`, `E1010`을 사용한다.

### 2649.6 Audit
- 이벤트에 `SwapExecutionPolicy.id`, `policy_version`, `access_mode`, (적용 시) `router` 주소를 기록한다.
- ReplayProtection이 활성화된 경우 `replay_protection_id`, `policy_version`, `scope_hash` 및 사용된 `request_id`의 해시를 기록한다(원문 저장은 정책으로 제한 가능).
- 제한 풀에서 Compliance 체크가 수행된 경우, 체크 결과의 해시/결정 코드만 기록하고 민감정보 원문 저장을 금지한다.

### 2649.7 Invariants
- 어떤 스왑도 EAF 승인 없이 풀 금고(vault) 또는 정책 객체를 변경할 수 없다.
- 제한 풀 정책은 “거부 또는 허용”만 수행하며, 가격/수량 산출의 결정론을 변경할 수 없다.
- ReplayProtection이 활성화된 경우, 동일 scope에서 동일 `request_id`의 재실행 Commit은 금지된다.


## 2650. 표준 이벤트(Event)·오류(Error)·감사(Audit) 레코드 규격(스왑)

### 2650.1 Purpose
스왑 실행의 사후 재현성, 분쟁 대응, 회계/감사를 위해 표준 이벤트 및 감사 레코드를 정의한다.

### 2650.2 Architecture or Rule
#### 2650.2.1 SwapExecutedEvent (Event)
```move
public struct SwapExecutedEvent has copy, drop {
  request_id: vector<u8>,
  tx_digest: vector<u8>,
  caller: address,
  recipient: address,
  mode: u8,
  amount_in: u64,
  amount_out: u64,
  total_fee_amount: u64,
  fee_policy_id: ID,
  fee_policy_version: u64,
  execution_policy_id: ID,
  execution_policy_version: u64,
  route_receipts: vector<HopReceipt>,
  fee_breakdown: vector<FeeLine>,
  timestamp_ms: u64,
}
```

#### 2650.2.2 SwapAuditRecord (Event 기반 표준)
- MVP 기준으로 **Event 기반 Audit을 표준(규범)** 으로 한다. On-chain Audit Object는 선택 구현으로만 허용한다.
- 최소 필드(감사 이벤트 또는 동일 이벤트 내 확장 필드로 제공):
  - 관련 객체 ID 목록(pool_id, vault_id, policy_id, guard_id, circuit_breaker_id, replay_protection_id)
  - before/after 스냅샷 해시(원문 상태 전체 저장은 선택)
  - BRVF/EAF 승인 결과 코드(성공 시 PASS 코드, 실패 시 해당 에러코드)
  - 실패 시 에러코드(Table 3 의미 유지)

### 2650.3 State/Flow
- 성공 시: `SwapExecutedEvent` + `SwapAuditRecord`(Event 기반) 기록 후 Commit.
- 실패 시: 상태 변경은 없으며, 선택적으로 `SwapFailedEvent`를 남길 수 있으나 성공 이벤트와 혼동 불가한 스키마로 분리한다.

### 2650.4 Validation
- 이벤트/감사 레코드 생성은 Commit의 일부로 간주하며, 기록 실패는 트랜잭션 Abort로 처리한다(감사 불가능한 Commit 금지).

### 2650.5 Failure handling
- 공통 오류코드 의미 유지:
  - `E1007`(규칙 위반), `E1008`(상태 오류), `E1006`(정책 버전 불일치) 등.
- 오류코드 의미를 재정의하거나 재사용 의미를 변경하는 행위는 금지한다.

### 2650.6 Audit
- 모든 스왑은 “정책 버전+라우트 영수증+수수료 분배”로 재현 가능해야 한다.
- 감사자는 이벤트 및 감사 레코드만으로 다음을 검증 가능해야 한다:
  - 슬리피지/한도 준수 여부
  - Oracle Guard/Circuit Breaker 적용 여부
  - 총 Fee와 분배 합의 일치 여부
  - 라우트별 입출금 보존 여부

### 2650.7 Invariants
- “Audit Recorded” 없이 Finality가 성립할 수 없다(상위 합의 원칙 준수).
- ReplayProtection이 활성화된 범위(scope)에서 동일 `request_id`에 대한 재실행이 탐지된 경우 Commit이 발생해서는 안 된다.
```

<-bash: cd: /home/boshin57/tobmate-agent-factory: No such file or SOURCE: workspace/drafts/3O_2651_2660_approved.md -->
```markdown
## 2651. 수수료·수익원 정의(Revenue Sources) 및 다중 수익 입력 모델(Multi-Revenue Input Model) — 개요

### Purpose
1. Gold Liquidity Pool Framework(GLPF)에서 발생하는 모든 수수료·수익원을 “정의된 가치 원천(Value Source)”으로 분류하고, 각 수익의 산출·귀속·감사 추적을 결정론적으로(on-chain deterministic) 기록하기 위한 입력 모델(Multi-Revenue Input Model)을 규정한다.
2. 헌법 원칙 “모든 경제적 보상은 정의되고 감사 가능한 가치 원천에 대응”을 실행 규칙으로 구체화한다.

### Architecture or Rule
1. GLPF는 수익을 **발생원(Revenue Source)** 과 **귀속(Allocation Target)** 을 분리하여 기록한다.
   1) 발생원: “왜 수익이 발생했는가(what/why)”
   2) 귀속: “누가 수익을 받을 자격이 있는가(who)”
2. 모든 수익 입력은 표준 불변 레코드(immutable on-chain record)인 `RevenueEvent`로 정규화되며, 이후 배분 엔진(Distribution Engine)은 레코드를 누적기(RevenueAccumulator)와 지수(RewardIndex)로 반영한다.  
   - 배분 엔진/누적기/지수의 구체 객체는 **본 배치의 후반 절(2656~2660)**에서 연결하며, 본 절에서는 **입력(ingress) 정의**만 확정한다.
3. 수익은 **확정(Recognized)** 과 **미확정(Accrued/Unrealized)** 을 엄격히 분리한다.  
   - GLPF에 “입금/징수/정산이 완료되어 프로토콜이 통제 가능한 자산(collectable asset)”으로 귀속된 경우에만 `RECOGNIZED`로 기록한다.
4. `RECOGNIZED`의 “프로토콜 통제”는 다음 요건을 동시에 만족해야 한다.
   1) 수령 자산이 `AllocationTargetType`별 격리 금고(vault)로 입금되었고, 해당 금고의 통제 권한(capability)이 프로토콜에 의해 강제되는 상태일 것
   2) 해당 입금/귀속이 Execution Authorization(헌법 4)의 승인 범주(Authorization Category)를 충족할 것  
      - 범주 정의는 [REFERENCE_REQUIRED]: Execution Authorization Framework
   3) 합의 최종성(consensus finality)이 확보된 트랜잭션 결과일 것(정상 커밋된 on-chain state)

### State/Flow
1. (거래/행위 발생) → 2. (Business Rule Validation) → 3. (Execution Authorization) → 4. (`RevenueEvent` 확정 기록) → 5. (`RevenueAccumulator` 반영) → 6. (배분 가능액(Distributable) 산정) → 7. (분배 인덱스 갱신 또는 청구가능액 적립)
2. 단계 분리 수행을 허용하는 경우, 상태 전이 경계와 최종성은 다음 2단계 상태 머신으로 고정한다.
   1) 1차 트랜잭션(TX1): `RevenueEvent`를 **불변(immutable)** 으로 확정 기록한다. TX1은 BRV/EAF 참조를 필수로 포함한다.
   2) 2차 트랜잭션(TX2): `revenue_event_id` 단일 참조로 누적기 반영을 수행하며, **멱등(idempotent) 가드**(예: `AppliedRevenueEventRegistry`)로 중복 반영을 금지한다. TX2 또한 BRV/EAF 참조를 필수로 포함한다.
3. TX1과 TX2가 분리된 경우에도, `RevenueEvent.recognition_status == RECOGNIZED`인 레코드만 누적기 반영 대상이 된다.

### Validation
1. `RevenueEvent`는 반드시:
   1) `value_source_type`가 본 장에서 정의된 열거(2652) 중 하나일 것
   2) `calculation_spec_id`(산출식 식별자)가 등록된 명세일 것
   3) `amount`가 0 초과이며, 입력 자산(denom)이 명시될 것
   4) 귀속 대상별 분해(allocations)가 총합(amount)과 정확히 일치할 것
   5) Treasury/Insurance/LP 등 자산 구분(segregation) 규칙을 위반하지 않을 것(최소 검증 요건은 2654 참조)
2. Recognized 조건:
   1) `recognition_status == RECOGNIZED`일 것
   2) `THIRD_PARTY_COST_PASS_THROUGH`는 **프로토콜 수익**으로 인식 금지(통과계정(pass-through)으로만 기록)
   3) Recognized에 필요한 수령 금고 및 승인 범주 증적이 감사 참조로 연결될 것(2657, 2658 참조)

### Failure handling
1. 검증 실패 시:
   - `RevenueEvent` 확정 기록 금지
   - 상태 변경 롤백
   - 실패 사유를 `RevenueError`로 표준화하여 로그/감사에 남긴다.
2. 외부 정산 지연(예: 오프체인 비용 확정 지연) 시:
   - `PENDING_SETTLEMENT` 상태로만 기록하고, `RECOGNIZED` 승격 전까지 누적기 입력 금지
   - 외부정산 프레임워크는 [REFERENCE_REQUIRED]

### Audit
1. 모든 `RevenueEvent`는 AuditTrail에 연결되어야 하며, 최소 필드는 다음을 포함한다.
   - 원인 트랜잭션/주문/포지션/풀/계정 식별자
   - 산출식 버전, 입력 파라미터, 라운딩 규칙
   - 귀속 분해 내역(대상별 금액) 및 target별 금고(vault) 식별자
2. 감사는 “이벤트 단위 재계산(recompute)”이 가능해야 한다(결정론).

### Invariants
1. (수익원-감사 가능성) 모든 분배/보상은 1개 이상의 `RevenueEvent`에 의해 뒷받침되어야 한다.
2. (자산 분리) Treasury, Insurance, Protocol Revenue, User/LP 자산은 동일 레코드 내에서라도 회계적으로 분리된 원장 항목(분리 vault/bucket)으로 기록되어야 한다.
3. (결정론) 동일 입력은 동일 `RevenueEvent`(동일 해시/동일 산출 결과)를 생성해야 한다.
4. [REFERENCE_REQUIRED]: section_index.md에 따른 2651~2660 배정 충돌 검증이 필요하다.


## 2652. 수익원(Value Source) 분류 체계

### Purpose
GLPF 및 연계 모듈에서 유입되는 수익을 표준 분류로 정의하여, 중복배분·혼합회계를 방지한다.

### Architecture or Rule
1. `ValueSourceType` 열거:
   1) `SWAP_FEE` : AMM/DEX 스왑 수수료
   2) `MINT_FEE` : GOLDPEG/FT/NFT 민트 과정의 프로토콜 수수료  
      - `OriginType == MINT_TX`인 경우 `reserve_attestation_ref` 또는 동등한 준비금 검증 참조가 필수(2656, 2653.2, 2658)
   3) `BURN_FEE` : 소각/상환 전환 과정의 프로토콜 수수료
   4) `REDEMPTION_PROTOCOL_FEE` : 실물 상환 처리 중 “프로토콜 관리 수수료”(제3자 실비 제외)
   5) `PENALTY_FEE` : 위약금/지연/규칙위반 페널티(정의된 규정 위반에 한함)
   6) `LIQUIDATION_FEE_SHARE` : 청산 수수료 중 GLPF 귀속분
   7) `BRIDGE_FEE_SHARE` : 브릿지 수수료 중 GLPF 귀속분
   8) `OTC_BLOCK_TRADE_FEE_SHARE` : OTC/RFQ/블록딜 집행 수수료 중 풀 귀속분
   9) `MARKETPLACE_FEE_SHARE` : NFT 마켓 수수료 중 풀/LP 연계 귀속분  
      - 연결 규칙(Registry) 등록 전까지 비활성(disabled)로 취급하며, 미등록 입력은 거절한다(Validation 참조).
   10) `EXTERNAL_PERMITTED_REVENUE` : 준비금 관련 허용수익/ETF 관련 허용수익 등 외부 수익 유입  
       - 상세 범주는 [REFERENCE_REQUIRED]: “Reserve-related Permitted Income”, “Gold ETF-related Permitted Income” 실행 프레임워크
2. 금지:
   1) `UNREALIZED_GAIN`(미실현 평가이익)은 분배 가능한 수익원으로 등록 금지
   2) `ACCRUED_NOT_COLLECTED`(미수/미징수)는 `RECOGNIZED` 수익원으로 등록 금지

### State/Flow
1. 각 수익원은 “발생 트리거(trigger)”와 “정산 확정(settlement finality)” 조건을 가진다(2653 참조).

### Validation
1. `EXTERNAL_PERMITTED_REVENUE`는:
   - 법적·회계적으로 허용된 범주임을 증빙하는 `external_attestation_id`를 요구한다([REFERENCE_REQUIRED]).
2. `MARKETPLACE_FEE_SHARE`는:
   - 연결 규칙 레지스트리(Registry) 등록이 필수이며, 미등록 시 `ERR_VALUE_SOURCE_DISABLED_OR_UNREGISTERED`로 거절한다. [REFERENCE_REQUIRED]: Marketplace Linking Registry

### Failure handling
1. 분류 불명/미등록 수익원 입력 시 `ERR_UNKNOWN_VALUE_SOURCE`로 거절한다.

### Audit
1. 수익원별 누적 및 분배 결과는 수익원 코드 단위로 분리 집계되어야 한다.

### Invariants
1. 수익원 코드는 불변(append-only)으로 관리하며 의미가 변경되지 않는다(버전 추가만 허용).


## 2653. 수익원별 발생 조건 및 산출식(Calculation Spec)

### Purpose
각 수익원이 언제, 어떻게(공식) 산출되는지 명시하여 재계산 가능한 감사 및 결정론을 보장한다.

### Architecture or Rule
1. 모든 산출식은 `CalculationSpec`로 등록되며 `calculation_spec_id`로 참조한다.
2. 산출식은:
   - 입력 파라미터(예: 금액, 비율, 라운딩)
   - 라운딩 규칙
   - 상한/하한(캡/플로어)
   - 면제 조건
   - **라운딩 잔차 처리 규칙(`residual_allocation_target`)**
   - **자격(eligibility) 및 대체 귀속(fallback allocation) 규칙의 참조(필요 시)**
   을 명시해야 한다.

### State/Flow
1. (거래 체결) → (산출식 평가) → (fee_amount 산출) → (allocations 분해) → (`RevenueEvent` 기록)

### Validation
1. 산출 결과는 다음을 만족해야 한다.
   1) `fee_amount <= base_amount` (정의된 경우)
   2) 라운딩으로 인한 잔차는 `rounding_residual` 필드에 기록한다.
   3) 잔차 처리 타겟은 반드시 `CalculationSpec.residual_allocation_target`로 지정되어야 하며, 미지정 시 트랜잭션 실패로 처리한다(기본값 금지).

### Failure handling
1. 산출식 평가 실패(오버플로/파라미터 누락) 시 트랜잭션 실패로 처리한다.

### Audit
1. 감사자는 산출식 버전과 입력값으로 fee_amount를 재현할 수 있어야 한다.

### Invariants
1. 동일 `calculation_spec_id` 및 동일 입력값은 동일 산출을 보장해야 한다.

---

### 2653.1 SWAP_FEE 산출식

#### Purpose
AMM 스왑에서 LP/프로토콜/보험 귀속 수수료를 결정한다.

#### Architecture or Rule
1. 정의:
   - `trade_amount` : 스왑 기준 금액(풀 정의에 따름)
   - `total_fee_rate` : 총 수수료율
   - `lp_fee_rate`, `protocol_fee_rate`, `insurance_fee_rate` : 귀속별 수수료율
2. 산출:
   - `total_fee = trade_amount × total_fee_rate`
   - `lp_fee = trade_amount × lp_fee_rate`
   - `protocol_fee = trade_amount × protocol_fee_rate`
   - `insurance_fee = trade_amount × insurance_fee_rate`
3. 제약:
   - `lp_fee_rate + protocol_fee_rate + insurance_fee_rate = total_fee_rate`

#### State/Flow
1. SwapEngine 체결 시 `RevenueEvent{SWAP_FEE}` 확정 기록 후, 누적기에 반영한다.

#### Validation
1. 풀별 위험 설정에 따라 `total_fee_rate` 상한을 둘 수 있다(상한값은 풀 파라미터로 고정).

#### Failure handling
1. 풀 파라미터 불일치 시 swap 자체를 거절한다.

#### Audit
1. 체결 내역(입출금 토큰, 가격, 슬리피지)과 fee 산출 입력을 함께 보존.

#### Invariants
1. 스왑 수수료는 사용자 자산에서 원천징수되며, 미징수 상태로 배분 입력 금지.

---

### 2653.2 MINT_FEE / BURN_FEE 산출식

#### Purpose
민트/소각(상환 전환 포함) 과정에서 발생하는 프로토콜 수수료를 정의한다.

#### Architecture or Rule
1. 정의:
   - `mint_amount` 또는 `burn_amount`
   - `mint_fee_rate` 또는 `burn_fee_rate`
2. 산출:
   - `mint_fee = mint_amount × mint_fee_rate`
   - `burn_fee = burn_amount × burn_fee_rate`
3. 귀속은 최소 다음 버킷으로 분해 가능:
   - `TREASURY`
   - `INSURANCE`
   - `LP`(유동성 안정화에 기여한 풀로 제한; 자격 규칙은 2655)
4. 준비금 선행 연결:
   - `MINT_FEE`의 `OriginType == MINT_TX`는 `reserve_attestation_ref`(또는 동등한 준비금 검증 참조) 없이는 입력 금지

#### State/Flow
1. 민트/소각 실행 완료 시점에만 `RECOGNIZED`로 입력한다(준비금 검증/소각 확정 전 입력 금지).

#### Validation
1. 준비금 선행(Verified reserve precedes issuance) 위반 시 `ERR_RESERVE_NOT_VERIFIED`.
2. `MINT_TX`의 경우 `reserve_attestation_ref` 누락 시 `ERR_MISSING_RESERVE_ATTESTATION`.

#### Failure handling
1. 민트/소각이 실패하거나 롤백되면 `RevenueEvent`도 생성되지 않는다.

#### Audit
1. 준비금 증명/소각 증명 식별자와 연결되어야 한다.

#### Invariants
1. 민트 수수료는 준비금·소유권 불변식을 우회하여 유동성 조작에 사용될 수 없다.

---

### 2653.3 PENALTY_FEE 산출식

#### Purpose
규칙 위반/지연/불이행에 대한 페널티를 표준화한다.

#### Architecture or Rule
1. 페널티는 반드시 “위반 타입(violation_type)”에 종속되며 임의 부과 금지.
2. 산출 방식 예:
   - 정액(fixed)
   - 비율(percent of obligation)
   - 시간 기반(time-decay/late fee)
3. 귀속 원칙:
   - 피해 복구/보험 재원 보강/프로토콜 운영비를 분리 기재(혼합 금지)

#### State/Flow
1. 위반 확정(Execution Authorization 포함) 시 `RevenueEvent{PENALTY_FEE}` 확정 기록.

#### Validation
1. 위반 증빙(온체인 상태/서명/오라클 증명) 없이는 입력 금지.

#### Failure handling
1. 분쟁 상태에서는 `DISPUTED_HELD`로만 기록([REFERENCE_REQUIRED]: 분쟁/보류 프레임워크).

#### Audit
1. 위반 근거 상태와 페널티 산출 파라미터를 연결한다.

#### Invariants
1. 페널티는 소유권 NFT(Principal ownership)를 침묵적으로(dilute/silent) 훼손하는 방식으로 징수할 수 없다.


## 2654. 수익 귀속 대상(Allocation Target) 분리 및 원장 격리

### Purpose
동일 레코드에서 발생한 수익이라도 귀속 대상에 따라 분리 회계/격리 보관을 강제한다.

### Architecture or Rule
1. `AllocationTargetType`:
   1) `LP` : 풀 기여자
   2) `TREASURY` : 프로토콜 운영/개발 재원
   3) `INSURANCE` : 보험/리스크 완충
   4) `PROTOCOL_REVENUE` : 프로토콜 수익(최초 기록 및 보관은 반드시 분리)
   5) `THIRD_PARTY_COST_PASS_THROUGH` : 제3자 실비 통과계정(수익 아님)
2. 원장 격리 규칙(ledger segregation) — 최소 구현 요건:
   1) 모든 `RevenueAllocation`은 `vault_id: ID`(또는 `target_ref`가 곧 vault임을 강제)를 포함해야 한다.
   2) 서로 다른 `AllocationTargetType`은 서로 다른 `vault_id`를 반드시 참조해야 한다(혼재 저장 금지).
   3) `vault_id`는 (target_type, denom) 단위로 결정 가능한 분리 스키마를 따라야 한다. [REFERENCE_REQUIRED]: Vault Registry/Schema
3. `PROTOCOL_REVENUE`의 Treasury/Insurance 재배분은 본 절에서 허용 가능성만 선언하며, 구체 전이(예: `ProtocolRevenueVault → TreasuryVault/InsuranceVault`)는 [REFERENCE_REQUIRED]로 분리한다.

### State/Flow
1. `RevenueEvent` → allocations[] 생성 → allocation별 `vault_id`로 분리 입금(또는 내부 계정 분리 기록)

### Validation
1. allocations 합계 검증:
   - `Σ allocations[i].amount == RevenueEvent.amount`
2. 타겟 적격성:
   - `LP` 귀속은 자격(eligibility) 충족 시에만 허용(2655)
3. 격리 검증:
   - 동일 `RevenueEvent` 내에서 `target_type`이 다른 allocation의 `vault_id`가 동일하면 `ERR_LEDGER_SEGREGATION_VIOLATION`

### Failure handling
1. 타겟 vault 미존재/락 상태면 레코드 확정 및 자산 이동을 거절한다(부분 성공 금지).

### Audit
1. 레코드 단위로 “타겟별 입금 증적(balance delta)”을 재구성할 수 있어야 한다.

### Invariants
1. Treasury/Insurance/사용자 자산의 혼합은 어떤 경로로도 허용되지 않는다.


## 2655. LP 자격(Eligibility) 기반 수익 입력 제한

### Purpose
모든 LP가 모든 수익을 수령할 수 없다는 원칙을 입력 단계에서 강제하여, 부당한 수익 이전을 방지한다.

### Architecture or Rule
1. `EligibilityRuleSet`(개념 규격):
   - `eligible_pool_id` 또는 `eligible_position_type`
   - `min_lock_duration`
   - `min_liquidity_depth`
   - `risk_adjustment_factor` 적용 여부
   - `cap_per_lp`(풀 장악 방지 상한) 적용 여부
   - `fallback_allocation_policy_ref`(eligible units가 0일 때의 처리 정책; 기본값 금지)
2. 수익원별 기본 연결:
   1) `SWAP_FEE` → 해당 풀 LP만 eligible
   2) `MINT_FEE` → “Initial Liquidity Support Pool”만 eligible (정의는 풀 태그로 식별)
   3) `BURN_FEE` / `REDEMPTION_PROTOCOL_FEE` → “Redemption Liquidity Support Pool”만 eligible
   4) `OTC_BLOCK_TRADE_FEE_SHARE` → 거래에 사용된 유동성 원천 풀 LP만 eligible
3. 본 절은 “입력 제한”만 정의하며, 실제 배분 방식(인덱스/청구)은 후속 절에서 정의한다.

### State/Flow
1. `RevenueEvent` 생성 시 `eligibility_context`를 함께 기록:
   - `pool_id`
   - `epoch`
   - `eligible_lp_units_snapshot_id`(또는 결정론적 스냅샷 파생키)
   - `eligibility_ruleset_ref`

### Validation
1. `LP` 귀속 allocation은:
   1) `eligibility_context`가 존재하고
   2) 해당 수익원에 매핑된 RuleSet을 충족하며
   3) 스냅샷 기준으로 “배분 단위(eligible units)”가 0이 아님이 검증되어야 한다.
2. eligible units가 0인 경우:
   - `fallback_allocation_policy_ref`가 **명시된 경우에만** 처리하며, 미지정이면 `ERR_NO_ELIGIBLE_UNITS`로 실패한다(기본 대체 귀속 금지).
3. `fallback_allocation_policy_ref`는 승인 참조(EAF/DAO 등)를 가져야 하며, 감사 참조에 포함되어야 한다. [REFERENCE_REQUIRED]: Policy Registry + Authorization Linkage

### Failure handling
1. 자격 검증 실패 시 `LP` allocation 생성 자체를 금지하며, 위 2항 정책이 없으면 트랜잭션 실패로 처리한다.

### Audit
1. 스냅샷/규칙/결과의 3자 연결(eligibility_ruleset_ref, snapshot_id, revenue_event_id)이 가능해야 한다.

### Invariants
1. 자격 없는 LP에게 수익이 이전되지 않는다.


## 2656. RevenueEvent 표준 객체 모델(입력 불변 레코드)

### Purpose
모든 수익 입력을 단일 표준 불변 레코드로 정규화하여 감사·집계·배분을 단순화한다.

### Architecture or Rule
1. `RevenueEvent`는 로그(event)가 아니라, 감사/중복방지/참조가능성을 위해 **불변 온체인 레코드(immutable on-chain record)** 로 저장된다.
2. 표준 객체(개념/구현 지향; Move 구조체는 본 장의 구현 절에서 확정):
   - `RevenueEvent`
     - `revenue_event_id: ID`
     - `timestamp_ms: u64`
     - `epoch: u64`
     - `recognition_status: u8` (2658)
     - `recognition_ref: ID?` (정산증빙/승격근거; 2658)
     - `value_source_type: u16` (2652)
     - `calculation_spec_id: ID`
     - `pool_id: ID?`
     - `position_ref: ID?` (LP position, strategy position 등)
     - `denom: TypeTag` (자산 단위)
     - `amount: u128`
     - `allocations: vector<RevenueAllocation>`
     - `eligibility_context: EligibilityContext?`
     - `origin_ref: OriginRef` (필수)
     - `reserve_attestation_ref: ID?` (MINT_TX 필수; 2652, 2653.2)
     - `attestations: vector<AttestationRef>` (외부 수익/비용 증빙; [REFERENCE_REQUIRED])
     - `rounding_residual: u128`
     - `hash: vector<u8>` (결정론적 해시; 입력 정규화 규칙 필요)
3. `RevenueAllocation`
   - `target_type: u8` (2654)
   - `vault_id: ID` (2654 최소 구현 요건)
   - `target_ref: ID?` (예: 특정 보험 서브풀, 특정 Treasury 버킷; [REFERENCE_REQUIRED])
   - `amount: u128`
4. `OriginRef`
   - `origin_type: u8` (아래 `OriginType` 열거)
   - `origin_id: ID`
5. `OriginType` 열거(본 배치에서 입력 레벨 고정):
   1) `SWAP_TX`
   2) `MINT_TX`
   3) `BURN_TX`
   4) `REDEEM_REQ`
   5) `LIQUIDATION_TX`
   6) `BRIDGE_TX`
   7) `OTC_TX`
   8) `MARKETPLACE_TX`
   9) `EXTERNAL_REVENUE_TX`
   - 각 origin_type별 상세 참조 규격은 [REFERENCE_REQUIRED]: Origin Reference Schema Registry

### State/Flow
1. 경제 행위 모듈은 반드시 (a) `RevenueEvent`를 확정 기록한 뒤, (b) 누적기 반영 함수를 호출한다.
2. 누적기 반영은 “레코드→상태”의 순서를 고정하여 결정론을 유지한다.
3. 누적기 반영은 `AppliedRevenueEventRegistry`(개념)로 중복 반영을 금지해야 한다.

### Validation
1. `hash`는 다음을 포함하는 정규화된 직렬화(canonical serialization)에 기반해야 한다.
   - (recognition_status, value_source_type, calculation_spec_id, pool_id, denom, amount, allocations, origin_ref, epoch)
2. `origin_ref`는 반드시 존재해야 한다(고아 수익 금지).
3. origin_type별 필수 참조:
   1) `SWAP_TX`는 `pool_id`가 필수
   2) `MINT_TX`는 `reserve_attestation_ref`가 필수
   3) `REDEEM_REQ`는 제3자 비용 통과계정이 포함될 수 있으나, `THIRD_PARTY_COST_PASS_THROUGH`는 `recognition_status == RECOGNIZED`로도 수익 취급 금지
   4) 나머지 상세 필수 필드는 [REFERENCE_REQUIRED]: Origin Reference Schema Registry

### Failure handling
1. 동일 `hash`의 중복 입력은 거절한다(`ERR_DUPLICATE_REVENUE_EVENT`).

### Audit
1. `RevenueEvent`는 감사 트레일의 “1차 원본 레코드(source of truth)”이다.

### Invariants
1. 모든 배분/보상 상태 변경은 하나 이상의 `RevenueEvent`로부터만 유도된다(직접 크레딧 금지).


## 2657. RevenueEvent → AuditTrail 연결 규칙

### Purpose
수익 입력이 “어떤 가치 원천에서 발생했고 누가 승인했는지”를 감사 가능하게 연결한다.

### Architecture or Rule
1. 본 절은 새로운 감사 객체를 재정의하지 않으며, 기존 Immutable Audit 레코드/레지스트리([REFERENCE_REQUIRED])에 `revenue_event_id` 및 승인 참조를 첨부하는 확장 규칙만 정의한다.
2. 감사 레코드는 최소 다음 참조를 포함해야 한다(명칭은 상위 프레임워크에 종속; 본 절은 필드 의미만 강제).
   - `revenue_event_id`
   - `business_rule_validation_ref`
   - `execution_authorization_ref`
   - `authorization_category`(Recognized 통제/수령 금고와 연계되는 승인 범주; [REFERENCE_REQUIRED])
   - `signers: vector<address>`(해당 프레임워크가 서명자를 기록하는 경우)
   - `state_before_digest`, `state_after_digest`(지원되는 경우)
   - `notes`(규제/회계 메모)

### State/Flow
1. `RevenueEvent` 확정 기록 → 감사 레코드에 `revenue_event_id` 첨부(또는 상호 링크) → 누적기 반영

### Validation
1. BRV/EAF 참조 누락 시 `RevenueEvent`는 invalid로 간주하며 누적기 반영 금지.
2. 외부 수익 입력(`EXTERNAL_PERMITTED_REVENUE`)은 외부 증빙 참조 및 승인 요건을 만족해야 한다([REFERENCE_REQUIRED]).

### Failure handling
1. 감사 링크 생성 실패 시 누적기 반영 금지.

### Audit
1. 감사자는 `revenue_event_id`에서 `origin_ref`까지 단방향으로 연결 가능해야 한다.

### Invariants
1. 감사 참조 없는 수익은 누적/배분 불가.


## 2658. 수익 확정(Recognition) 및 Distributable 판정 규칙

### Purpose
“확정 수익만 인식” 및 “미실현/미징수는 배분 금지” 원칙을 GLPF 입력 레벨에서 강제한다.

### Architecture or Rule
1. `RecognitionStatus`:
   1) `RECOGNIZED` : 프로토콜 통제 하에 실제로 수령/정산 완료
   2) `PENDING_SETTLEMENT` : 외부 정산 대기(배분 입력 금지)
   3) `DISPUTED_HELD` : 분쟁/보류(배분 입력 금지)
2. `RevenueEvent.recognition_status`는 필수 필드이며, 누적기 반영은 `RECOGNIZED`만 허용한다.
3. `RECOGNIZED` 판정은 다음을 모두 만족해야 한다.
   1) 수령 자산이 `RevenueAllocation.vault_id`로 지정된 격리 금고에 반영되었을 것
   2) 해당 반영에 필요한 Execution Authorization이 승인되었고, 감사 레코드에 `execution_authorization_ref` 및 `authorization_category`가 연결되었을 것([REFERENCE_REQUIRED])
   3) 온체인 합의 최종성으로 커밋된 상태일 것
4. Distributable은 다음을 충족해야 한다.
   - `recognition_status == RECOGNIZED`이며
   - `AllocationTargetType == THIRD_PARTY_COST_PASS_THROUGH`가 아니고
   - 해당 수익원의 “보호 적립(reserve holdback)” 규칙을 적용한 잔액일 것  
     - 구체 적립/재배분 규칙은 [REFERENCE_REQUIRED]: Treasury/Insurance Framework

### State/Flow
1. `PENDING_SETTLEMENT` → (정산 증빙 제출) → (`RECOGNIZED`로 승격)
2. 승격은 다음 중 하나로 기록되어야 한다.
   1) 동일 `revenue_event_id`에 대해 `recognition_ref`를 추가하는 불변 승격 레코드(권장) [REFERENCE_REQUIRED], 또는
   2) `RevenueEvent` 자체가 생성 시점부터 `RECOGNIZED`로 확정 기록(사후 변경 금지)

### Validation
1. 미실현 평가이익은 어떤 경로로도 `RECOGNIZED` 승격 금지.
2. 미징수/미수 수수료는 `PENDING_SETTLEMENT`로만 기록 가능하며 누적기 반영 금지.

### Failure handling
1. 승격 증빙 불충분 시 상태 유지, 배분 불가.

### Audit
1. 승격은 반드시 `recognition_ref`로 증빙을 연결해야 한다([REFERENCE_REQUIRED]).

### Invariants
1. Accrued Fee ≠ Collected Revenue, Unrealized Gain ≠ Distributable Revenue를 시스템 규칙으로 강제한다.


## 2659. Treasury/Insurance 연결 선언(본 절의 경계)

### Purpose
본 배치(2651~2660)가 Treasury/Insurance 프레임워크의 상세를 선행 정의하지 않도록 경계를 명확히 한다.

### Architecture or Rule
1. 본 절은 다음을 “선언”만 한다.
   1) AllocationTarget으로 `TREASURY`, `INSURANCE`, `PROTOCOL_REVENUE`를 사용한다.
   2) 타겟별 vault/계정은 분리되어야 한다.
   3) `PROTOCOL_REVENUE`에서 `TREASURY`/`INSURANCE`로의 재배분 전이는 본 절에서 정의하지 않는다. [REFERENCE_REQUIRED]
   4) 구체 vault 구조, 재배분, 적립률(holdback), 집행 권한은 Chapter 3O 후반의 Treasury/Insurance 절에서 정의한다. [REFERENCE_REQUIRED]

### State/Flow
1. `RevenueEvent.allocations[]`는 향후 Treasury/Insurance 모듈이 소비 가능한 표준 입력으로 유지된다.

### Validation
1. Treasury/Insurance 모듈 미탑재 시에도 `RevenueEvent` 확정 기록은 가능하되, 해당 타겟으로의 실자산 이동은 “미결(escrow/queued)” 상태로만 처리되어야 한다([REFERENCE_REQUIRED]).
2. “미결(escrow/queued)”은 `RECOGNIZED`와 혼동되지 않도록 별도 상태 코드/증빙으로 구분해야 한다([REFERENCE_REQUIRED]).

### Failure handling
1. 연결 모듈 부재로 인한 자산 이동 실패는 부분 성공을 허용하지 않으며, 큐잉/보류 규칙이 필요하다([REFERENCE_REQUIRED]).

### Audit
1. 큐잉/보류 상태는 감사상 “미지급 확정채무”로 오인되지 않도록 상태 코드로 구분한다.

### Invariants
1. Treasury/Insurance의 자산 격리 원칙은 입력 단계에서부터 위반될 수 없다.


## 2660. 헌법 준수 체크리스트(입력 모델 관점)

### Purpose
본 배치가 헌법 불변식을 침해하지 않음을 “입력 단계 규칙”으로 고정한다.

### Architecture or Rule
1. (준비금 선행) 민트 관련 수익원(`MINT_FEE` 등)은 Verified reserve 선행 없이는 입력 불가이며, `reserve_attestation_ref`로 증빙이 연결되어야 한다.
2. (원금 소유권 보호) Principal ownership NFT/권리 객체의 소유권을 침묵적으로 훼손하는 방식(강제 소각/자동 이전/무기록 차감)으로 수익을 만들거나 배분할 수 없다.
3. (권리 분리) NFT(ownership)와 FT(utility/liquidity)의 권리를 혼합하여 “보유만으로 자동 수익”을 생성하지 않는다. 수익은 가치 원천 레코드(`RevenueEvent`)에 의해 발생해야 한다.
4. (검증·권한) 모든 `RevenueEvent`는 Business Rule Validation 및 Execution Authorization 참조가 필수이며, `RECOGNIZED`는 승인 범주 및 수령 금고(vault) 통제 요건을 만족해야 한다.
5. (유동성 우회 금지) 어떤 수익도 준비금/소유권/합의/감사 불변식을 우회하여 LP 또는 특정 주체에 직접 전송될 수 없다.
6. (결정론) 동일 입력은 동일 출력(`RevenueEvent.hash`/산출액/allocations)을 생성해야 한다.
7. (가치 원천) 모든 보상은 정의된 `ValueSourceType` 및 등록된 `CalculationSpec`에 의해 설명 가능해야 한다.
8. (자산 분리) Treasury/Insurance/Protocol Revenue/User 자산은 입력·원장에서 분리(vault_id 분리)되어야 한다.
9. (추적성) Redemption/burn/settlement 관련 수익은 `origin_ref`로 사건 단위 추적이 가능해야 한다.
10. (확장 호환) 신규 수익원 추가는 `ValueSourceType` append-only 및 `CalculationSpec` 추가로만 수행한다.
11. [REFERENCE_REQUIRED]: section_index.md 기준 번호 충돌이 확인될 경우, 본 배치 번호는 재배정되어야 하며 의미 변경 없이 이동한다.

### State/Flow
1. 체크리스트 위반은 입력 거절 또는 보류로만 처리하며, 사후 보정으로 합법화하지 않는다.

### Validation
1. 체크리스트 위반 코드는 `ConstitutionalViolation`로 표준화하여 트랜잭션을 실패시킨다.

### Failure handling
1. 위반 발생 시:
   - `RevenueEvent` 미발행
   - 관련 상태전이 중단
   - 감사 로그에 위반 항목과 입력 파라미터를 기록

### Audit
1. 감사자는 임의의 보상 지급(Claim/Withdraw/Distribution)이 어떤 `RevenueEvent` 및 체크리스트를 통과했는지 역추적 가능해야 한다.

### Invariants
1. “정의·감사 가능한 가치 원천 없는 보상”은 시스템적으로 불가능해야 한다.
```

<-bash: cd: /home/boshin57/tobmate-agent-factory: No such file or SOURCE: workspace/drafts/3O_2661_2670_approved.md -->
```markdown
## 2661. 분배 엔진(Distribution Engine) 개요

### 2661.1 Purpose
분배 엔진(Distribution Engine)은 GLPF에서 발생하는 수익(Revenue) 및 비용성 항목(예: 손실 보전 적립)을 **Treasury/Insurance/DAO**로 **결정론적(deterministic)** 으로 라우팅하고, 모든 분배를 **Validation → Authorization → (Governance/Validator Approval) → On-chain Finality(Consensus) → Audit** 순서로 실행하기 위한 표준 인터페이스 계층을 정의한다.

### 2661.2 Architecture or Rule
1. 분배 엔진은 **유동성 풀 실행 계층(Execution Layer)** 에 속하되, **준비금(Reserve)·원금 소유권(NFT)·자산 분리(Segregation) 불변식**을 우회할 수 없다.
2. 분배 엔진은 다음 상위 객체/모듈과의 결합 지점을 가진다(미정의 항목은 인터페이스 계약으로 제한한다).
   - TreasuryRegistry 조회 및 TreasuryVault 이체 인터페이스(Transfer Interface) — [REFERENCE_REQUIRED]
   - InsuranceReserve 적립 인터페이스(Accrual Interface) — [REFERENCE_REQUIRED]
   - DAO Governance 정책 변경 훅(Parameter Change Hook) — [REFERENCE_REQUIRED]
3. 분배 엔진은 **사용자 자산(User Assets)**, **프로토콜 자산(Protocol Assets)**, **보험 자산(Insurance Assets)** 을 단일 Vault로 혼합 보관하거나 상호 대체하여 이동시키는 것을 금지한다.
4. (입력 적격성 고정) 분배 엔진은 **UserVault(사용자 예치/포지션)에서 직접 차감**하거나, 사용자 잔고를 분배 입력으로 간주하는 경로를 **일절 허용하지 않는다**. 분배 엔진이 처리할 수 있는 금액은 오직 원천 모듈이 사전에 **프로토콜 귀속 확정(settled-to-protocol)** 하여 **ProtocolRevenueVault**(또는 동등한 “프로토콜 수익 누적 금고”)로 **분리 완료**한 금액으로 제한된다.
   - 사용자 서명에 의해 발생하는 공제/징수(예: 포지션 정산, 사용자 지시 수수료 납부)는 분배 엔진이 아니라 별도 모듈의 상태 전이로 처리되어야 하며, 해당 모듈은 분리 완료 후에만 RevenueEvent를 발생시킨다 — [REFERENCE_REQUIRED].

### 2661.3 State/Flow
분배 엔진의 표준 실행 흐름은 다음 순서를 고정한다(순서 변경 불가).
1. Fee/Revenue Source 확정(원천 이벤트 식별)
2. Business Rule Validation
3. Execution Authorization
4. (정책 변경 등 별도 승인 필요 시) Governance/Validator Approval 확인(체인 외/별도 절차의 결과 플래그)
5. Atomic Distribution Execution
6. On-chain Finality(Consensus): 트랜잭션은 체인 합의에 의해 최종화된다(기본 전제).
7. Audit Recording

### 2661.4 Validation
- 입력 수익원은 반드시 **정의된 Value Source**를 가져야 한다(정의되지 않은 수익 분배 금지).
- 입력 적격성(Eligibility): 정산 대상 금액은 `ProtocolRevenueVault`에 귀속 확정된 누적분으로 한정되며, `UserVault` 직접 차감/참조는 금지한다.
- 분배 합계 불변식: `total_generated = Σ(distributed_amounts)` 및 잔여/누락 금지(잔여는 2669 규칙에 따라 “정의된 방식”으로만 처리).
- 음수 금액, 중복 청구(duplicate claim), 이중 지급(double spend) 금지.
- 자산 분리 검증: 출금/이체의 source vault와 target vault는 정책상 허용된 조합이어야 한다.

### 2661.5 Failure handling
- 본 장의 에러코드 체계는 [REFERENCE_REQUIRED]로 위임한다. 본 섹션은 실패를 다음 범주로 고정한다.
  - ValidationFailure(규칙/합계/분리 위반)
  - AuthorizationFailure(권한/Capability/만료)
  - PolicyFailure(정책 누락/버전 불일치/비활성)
  - StateConflict(동일 epoch 경쟁, 커서 CAS 실패 등)
  - ReplayDetected(재실행/중복 정산 탐지)
- 실패 시 전체 분배는 원자적(atomic)으로 롤백되며, 부분 분배는 발생하지 않는다.

### 2661.6 Audit
- 모든 분배 실행은 `DistributionAuditRecord`를 남기며, 원천 이벤트 ID, 정책 버전, 라우트별 금액, 수신 금고 ID, 승인 주체를 포함해야 한다.

### 2661.7 Invariants
1. 자산 분리(Segregation): 사용자 자산/프로토콜 자산/보험 자산은 목적 외 전용 금지.
2. 결정론성: 동일 입력(동일 epoch, 동일 정책 버전, 동일 원천 이벤트) → 동일 출력 분배 결과.
3. 원자성: 분배는 전부 성공 또는 전부 실패.
4. 입력 적격성 불변: 분배 엔진은 UserVault 직접 차감을 입력으로 수용하지 않는다.


## 2662. 분배 라우팅 규칙(Routing Rule): 비율, 우선순위, 정산 주기(Epoch)

### 2662.1 Purpose
수익 분배를 비율(share), 우선순위(priority), 정산 주기(settlement epoch) 기준으로 표준화하여, GLPF의 모든 풀/시장/DeFi 모듈이 동일한 방식으로 Treasury/Insurance/DAO로 라우팅하도록 한다.

### 2662.2 Architecture or Rule
1. 분배 라우팅은 `DistributionPolicy`에 의해 정의된다.
2. 본 섹션에서 외부 프레임워크(TRF/IRF/DGF) 및 레지스트리 의존은 [REFERENCE_REQUIRED]로 표시하며, 대신 최소 인터페이스 계약(Interface Contract)을 고정한다.
   - TreasuryRegistry 인터페이스 계약(최소):
     - `get_treasury_record(treasury_id) -> (treasury_type, policy_id, status)`
     - `is_allowlisted_vault(vault_id) -> bool`
     - `resolve_treasury_vault(treasury_id) -> vault_id`
     - (정책/상태 조회의 결정론적 결과 보장) — [REFERENCE_REQUIRED]
   - InsuranceReserveRegistry/Policy 인터페이스 계약(최소) — [REFERENCE_REQUIRED]
3. 정책은 다음을 포함한다.
   - 분배 항목(Route) 목록: Treasury/Insurance/DAO/LP/Validator/Oracle 등
   - Route별 비율(share_bps)과 우선순위(priority)
   - 자산별 허용 대상 금고(vault allowlist)
   - 정산 주기(epoch_interval) 및 정산 시점 기준(epoch_anchor)
   - 잔액(remainder) 처리 규칙(2669와 일관)

### 2662.3 Object Model
```move
// 주의: UID/ID/Bag 및 TypeTag 표준은 [REFERENCE_REQUIRED]에 따른다.

public struct DistributionPolicy has key {
    id: UID,
    version: u64,
    status: u8,                 // 0 Active, 1 Frozen, 2 Deprecated
    epoch_interval: u64,        // 정산 주기 (must be > 0)
    epoch_anchor: u64,          // 기준 epoch
    routes: vector<DistributionRoute>,
    allowlisted_vaults: vector<ID>,
    remainder_rule: u8,         // 0 CarryToProtocolRevenueVault, 1 AssignToRouteByPriority
    created_at: u64,
    updated_at: u64
}

public struct DistributionRoute has store {
    route_type: u8,             // 0 Treasury, 1 Insurance, 2 DAO, 3 LPReward, 4 Validator, 5 Oracle, ...
    priority: u16,              // 낮을수록 우선
    share_bps: u32,             // basis points (총합=10000)
    target_ref: ID,             // TreasuryId/InsuranceReserveId/DaoRevenueVaultId 등(대상 타입은 route_type으로 결정)
    asset_rules: vector<AssetRule>
}

public struct AssetRule has store {
    asset_type_tag: vector<u8>, // canonical TypeTag bytes (결정론적 인코딩 요구)
    min_amount: u64
}
```

### 2662.4 State/Flow
1. (원천) `RevenueEvent` 발생 및 누적(Accumulate)
2. epoch 전환 또는 임계치 도달 시 `settle(epoch)` 호출
3. 정책 버전 고정(`policy.version`) 후 라우트 계산
4. **정수 계산 표준 알고리즘(결정론 고정)**:
   1) 모든 라우트에 대해 `amount_i = floor(total * share_bps_i / 10000)`으로 1차 산출  
   2) `remainder = total - Σ amount_i` 계산  
   3) `remainder_rule`에 따라 remainder를 처리(2669.2-2669.3 참조)  
5. 우선순위 순으로 라우트 실행(단, **전체는 atomic**)
6. 감사기록 생성

### 2662.5 Validation
- `Σ share_bps == 10000` 강제.
- `epoch_interval > 0` 강제.
- `current_epoch >= epoch_anchor` 강제.
- epoch 계산은 checked arithmetic으로 평가하며, `((current_epoch - epoch_anchor) % epoch_interval == 0)` 조건을 만족해야 정산 가능.
- 동일 route_type 중복 허용 여부는 정책으로 결정하되, 중복 시에도 **우선순위(priority)와 target_ref를 포함한 정렬이 결정론적**이어야 한다.

### 2662.6 Failure handling
- ValidationFailure: bps 총합 불일치, epoch 조건/경계 위반, allowlist 위반.
- PolicyFailure: 정책 비활성/동결/폐기 상태.
- StateConflict: 동일 epoch에 대한 중복 settle 시도는 커서 CAS 실패로 전량 롤백(2663.6 참조).

### 2662.7 Audit
- `DistributionSettleAudit`에 `epoch`, `policy_version`, `routes_hash`, `total_generated`, `total_distributed`, `remainder`, `remainder_rule` 기록.

### 2662.8 Invariants
1. 비율 총합 불변: 10000 bps.
2. 정산 주기 불변: 정책 버전 고정 후에는 해당 정산 트랜잭션 동안 변경 불가(동일 TX 내).
3. 계산 알고리즘 불변: floor 기반 1차 산출 + 단일 remainder 처리 규칙.


## 2663. 수익 원천 이벤트(Revenue Event) 모델 및 정산 단위

### 2663.1 Purpose
모든 경제적 분배는 감사 가능한 원천(Value Source)에 기반해야 하므로, 수익/비용 발생을 표준 이벤트로 캡처하고 중복 정산을 방지한다.

### 2663.2 Architecture or Rule
1. 분배 엔진은 오직 `RevenueEvent`(또는 `LossProvisionEvent`)로 표현된 원천에 대해서만 정산한다.
2. (입력 적격성 고정) `RevenueEvent.amount`는 원천 모듈이 **사용자 자산에서 분리하여** **ProtocolRevenueVault로 귀속 확정(settled-to-protocol)** 한 금액만을 의미한다. `RevenueEvent`를 근거로 분배 엔진이 `UserVault`에서 직접 차감하는 실행 경로는 금지된다.
3. (유일성 규칙 고정) 이벤트의 유일 키는 `(scope_type, scope_id, epoch, nonce)`로 고정한다. `nonce`는 해당 scope 내에서 단조 증가해야 한다.

### 2663.3 Object Model
```move
public struct RevenueEvent has store {
    scope_type: u8,         // 0 Global, 1 ByPool, 2 ByMarket
    scope_id: ID,           // PoolId/MarketId 등
    source_type: u8,        // 0 TradingFee, 1 LiquidityFee, 2 PremiumFee, 3 MarketplaceFee, 4 OracleFee, ...
    asset_type_tag: vector<u8>, // canonical TypeTag bytes
    amount: u64,            // settled-to-protocol amount only
    epoch: u64,
    nonce: u64,             // monotonic per (scope_type, scope_id)
    occurred_at: u64
}

public struct SettlementCursor has key {
    id: UID,
    scope_type: u8,
    scope_id: ID,
    last_settled_epoch: u64,
    last_settled_nonce: u64
}
```

### 2663.4 State/Flow
1. 원천 모듈이 `emit RevenueEvent`(settled-to-protocol 의미를 만족해야 함)
2. 분배 엔진이 이벤트를 epoch별로 집계(구현은 event-sourcing 또는 누적 vault; 구현 선택은 모듈 내부)
3. `SettlementCursor` 기준으로 미정산 범위만 정산
4. 정산 완료 시 cursor 업데이트(CAS 규칙 적용)

### 2663.5 Validation
- `nonce`는 동일 `(scope_type, scope_id)` 내에서 단조 증가해야 한다.
- cursor보다 과거 이벤트는 정산 대상에서 제외(재실행 방지).
- `(epoch, nonce)`가 cursor에 의해 이미 포함된 범위이면 ReplayDetected로 처리한다.

### 2663.6 Failure handling
- ReplayDetected: nonce 역행/중복, 이미 정산된 범위 재정산 시도.
- StateConflict(경쟁 상태) 결정 규칙:
  - `SettlementCursor` 업데이트는 compare-and-swap(CAS) 의미를 가져야 하며, **cursor가 기대값과 일치할 때만** 정산 트랜잭션이 성공한다.
  - CAS 실패 시 트랜잭션은 전량 롤백되고, 다음 트랜잭션에서 **동일 입력 집합에 대해 동일 결과**가 재계산되어야 한다(결정론 유지).

### 2663.7 Audit
- 정산에 포함된 `(scope_type, scope_id, epoch, nonce_range)` 및 총합을 기록한다.

### 2663.8 Invariants
1. 동일 유일 키 `(scope_type, scope_id, epoch, nonce)`의 이벤트는 최대 1회만 정산된다.
2. 정산 커서는 후퇴하지 않는다.
3. RevenueEvent는 settled-to-protocol 의미를 위반할 수 없다.


## 2664. Treasury 이체(Transfer) 인터페이스

### 2664.1 Purpose
분배 결과를 Treasury 계정(또는 Treasury Object)으로 안전하게 이체하고, 목적별 Treasury 분리 원칙을 훼손하지 않도록 한다.

### 2664.2 Architecture or Rule
- 분배 엔진은 `TreasuryRegistry`가 반환하는 `TreasuryRecord` 및 정책을 통해서만 대상 Treasury를 식별한다 — [REFERENCE_REQUIRED].
- Treasury 유형별 금고는 목적 외 사용 금지이며, 분배 엔진은 **분배 목적과 Treasury 유형 매핑**을 강제한다.
- (인터페이스 계약 최소) TreasuryRegistry는 최소한 `treasury_type`, `status`, `vault_id`를 결정론적으로 해석 가능하게 제공해야 한다 — [REFERENCE_REQUIRED].

### 2664.3 Object Model (Interface)
```move
public struct TreasuryTransferRequest has store {
    policy_id: ID,
    policy_version: u64,
    treasury_id: ID,
    asset_type_tag: vector<u8>, // canonical TypeTag bytes
    amount: u64,
    source_ref: ID,          // Revenue source (PoolId 등)
    epoch: u64,
    nonce: u64
}

public struct TreasuryTransferReceipt has store {
    treasury_id: ID,
    asset_type_tag: vector<u8>,
    amount: u64,
    applied_at: u64,
    tx_digest: vector<u8>
}
```

### 2664.4 State/Flow
1. `TreasuryTransferRequest` 생성
2. Business Rule Validation:
   - treasury_id allowlist
   - treasury_type 매핑 일치
3. Execution Authorization:
   - Treasury Authorization(필수) — [REFERENCE_REQUIRED]
4. `MultiAssetTreasury`(또는 해당 Treasury Vault)로 `amount` 이체
5. Receipt 생성 및 감사기록

### 2664.5 Validation
- Treasury 분리 검증: treasury_type이 route 목적과 일치해야 한다.
- 자산 허용 검증: Treasury가 허용하는 asset_type_tag인지 확인.

### 2664.6 Failure handling
- ValidationFailure: 정책/목적-유형 매핑 불일치, allowlist 위반.
- AuthorizationFailure: Treasury 권한 미충족.
- PolicyFailure: Treasury 비활성/동결 상태 — [REFERENCE_REQUIRED].

### 2664.7 Audit
- `TreasuryTransferAuditRecord`: request, receipt, 정책버전, 승인 주체 포함.

### 2664.8 Invariants
1. 분배 엔진은 Treasury 간 상호 전용(transfer) 기능을 제공하지 않는다(분배 목적 외 재배치 금지).
2. Treasury 수신은 반드시 Treasury Authorization을 거친다.


## 2665. Insurance Reserve 적립(Accrual) 규칙 및 손실/리스크 이벤트 연계

### 2665.1 Purpose
프로토콜 손실 또는 리스크 이벤트에 대비하기 위해, 분배 수익의 일부를 Insurance Reserve로 **사전 적립**하고, 적립/사용을 엄격히 분리한다.

### 2665.2 Architecture or Rule
- Insurance Reserve는 사용자 자산 및 일반 Treasury와 분리된 별도 금고로 유지된다.
- 적립은 `InsuranceAccrualPolicy`에 의해 정의되며, 사용(지급)은 별도 손실 보전 절차([REFERENCE_REQUIRED])를 요구한다.
- Insurance Authorization 범주/Capability 명세는 [REFERENCE_REQUIRED]이며, 본 섹션은 최소 입력 계약만 고정한다:
  - `InsuranceAccrualCapability`는 `(insurance_reserve_id, policy_id, policy_version, asset_type_tag)`에 대해 적립 권한을 증명해야 한다 — [REFERENCE_REQUIRED].

### 2665.3 Object Model (Interface)
```move
public struct InsuranceAccrualRequest has store {
    policy_id: ID,
    policy_version: u64,
    insurance_reserve_id: ID,
    asset_type_tag: vector<u8>, // canonical TypeTag bytes
    amount: u64,
    reason_code: u16,      // 0 RoutineAccrual, 1 RiskTierIncrease, ...
    source_ref: ID,
    epoch: u64,
    nonce: u64
}

public struct InsuranceReservePosition has key {
    id: UID,
    reserve_id: ID,
    balances: Bag,
    last_accrued_at: u64,
    status: u8             // 0 Active, 1 Frozen
}
```

### 2665.4 State/Flow
1. 라우팅 결과 중 Insurance share 계산
2. `InsuranceAccrualRequest` 생성
3. Validation:
   - 보험 금고 allowlist
   - 최소 적립 기준(min_amount)
4. Authorization:
   - Insurance Authorization(필수) — [REFERENCE_REQUIRED]
5. InsuranceReservePosition으로 적립
6. 감사기록

### 2665.5 Validation
- 적립은 오직 분배 엔진의 정산 트랜잭션 컨텍스트에서만 허용(임의 적립/차입 금지).
- 보험 금고 상태가 `Active`가 아니면 거부.

### 2665.6 Failure handling
- PolicyFailure: 보험 금고 동결/비활성.
- AuthorizationFailure: 보험 적립 권한 실패.

### 2665.7 Audit
- `InsuranceAccrualAuditRecord`: reason_code, policy_version, reserve_id, amount, source_ref.

### 2665.8 Invariants
1. Insurance 자산은 Treasury 운영비로 전용 불가.
2. 적립과 사용은 동일 권한 범주로 묶지 않는다(적립 Authorization ≠ 지급 Authorization).


## 2666. DAO Governance 훅(Hook): 파라미터 변경 요청/승인 플로우

### 2666.1 Purpose
분배 비율, 우선순위, epoch 주기 등 핵심 파라미터 변경을 **DAO Governance 승인** 하에 수행하기 위한 표준 훅을 정의한다.

### 2666.2 Architecture or Rule
- 분배 정책 변경은 `PolicyUpdateProposal`로 표현되며, **DAO Authorization** 및 필요한 경우 **Validator Approval**을 요구한다 — [REFERENCE_REQUIRED].
- 헌법적 불변 항목은 일반 DAO 투표로 변경 불가이며, 해당 변경 시도는 즉시 거부한다(Constitutional Invariant).
- (최소 금지 항목 명시) 다음 변경은 헌법 불변 위반으로 간주되어 거부되어야 한다.
  1. 2667의 Segregation 매트릭스 완화(예: `UserVault -> ProtocolRevenueVault` 직접 허용, `InsuranceVault -> TreasuryVault` 허용).
  2. 2670의 Audit-Completeness 해제(감사 레코드 생성 선택화/비활성화).
  3. 2663의 입력 적격성 위반(RevenueEvent를 사용자 자산 직접 차감의 근거로 사용하는 구조).
- 검증은 `GovernanceValidator`(정책 검증기)가 수행하며 인터페이스는 [REFERENCE_REQUIRED]로 둔다.

### 2666.3 Object Model
```move
public struct PolicyUpdateProposal has key {
    id: UID,
    proposer: address,
    target_policy_id: ID,
    base_version: u64,
    new_policy_bytes: vector<u8>,   // 정책 직렬화(구현 선택)
    status: u8,                     // 0 Pending, 1 Approved, 2 Rejected, 3 Expired
    created_at: u64,
    voting_deadline_epoch: u64
}

public struct PolicyUpdateApproval has store {
    proposal_id: ID,
    dao_approved: bool,
    validator_approved: bool,       // 정책 변경과 같은 별도 절차 승인 의미(체인 합의 자체와 구분)
    approved_at: u64
}
```

### 2666.4 State/Flow
1. 제안 생성: `status=Pending`
2. GovernanceValidator로 사전 검증(헌법 불변 위반 탐지) — [REFERENCE_REQUIRED]
3. DAO 투표/심사 후 승인 시 `dao_approved=true`
4. 필요 범주(위험/중대 변경)에 해당하면 `validator_approved=true` 요구 — [REFERENCE_REQUIRED]
5. 승인 완료 후 정책 버전 증가 및 활성화
6. 감사기록

### 2666.5 Validation
- `base_version`은 현재 정책 버전과 일치해야 한다(동시성/경합 방지).
- 2666.2의 금지 항목을 포함하여 헌법 불변 위반 패턴이 검출되면 거부한다.

### 2666.6 Failure handling
- PolicyFailure: 제안 만료(`status=Expired`), 버전 불일치, 승인 플래그 불충족.
- AuthorizationFailure: DAO/Validator 승인 권한 실패 — [REFERENCE_REQUIRED].

### 2666.7 Audit
- Proposal lifecycle 전 단계에 대해 `PolicyGovernanceAuditRecord`를 남긴다.

### 2666.8 Invariants
1. 정책 버전은 단조 증가한다.
2. 승인 없이 정책 활성화 불가(DAO Authorization 불변).
3. validator_approved는 정책 변경 절차에만 적용되며, 트랜잭션 최종화(Consensus)를 대체하지 않는다.


## 2667. 자산 분리 보장(Segregation Guarantee): User vs Protocol vs Insurance

### 2667.1 Purpose
GLPF의 분배 및 라우팅 과정에서 자산 혼합을 구조적으로 차단하여, 사용자 자산 보호 및 회계/감사 가능성을 유지한다.

### 2667.2 Architecture or Rule
분배 엔진은 다음 금고/Vault 타입을 구분한다.
- `UserVault`: 사용자의 예치/포지션에 귀속
- `ProtocolRevenueVault`: 프로토콜 수익 누적(분배 엔진 입력은 원칙적으로 여기에 한정)
- `TreasuryVault`: 목적별 Treasury 수신
- `InsuranceVault`: 보험 적립/보유
- `DAORevenueVault`: DAO 수익 수신(또는 DAO Treasury로 귀속)

분배 엔진에서 허용되는 이동은 다음과 같이 제한한다.
1. ProtocolRevenueVault → TreasuryVault (허용)
2. ProtocolRevenueVault → InsuranceVault (허용)
3. ProtocolRevenueVault → DAORevenueVault (허용)
4. UserVault → (어떠한 Protocol/Treasury/Insurance/DAO Vault) (금지; 사용자 서명 트랜잭션 기반 공제/징수는 분배 엔진이 아닌 별도 모듈에서 처리) — [REFERENCE_REQUIRED]
5. InsuranceVault → TreasuryVault (금지; 손실보전 절차만 허용 [REFERENCE_REQUIRED])

### 2667.3 State/Flow
- (입력 경계 고정) 분배 엔진 입력은 `ProtocolRevenueVault` 누적분만 허용한다. `UserVault`로부터의 직접 입력, 또는 `UserVault` 잔고를 근거로 한 자동 차감 입력은 금지한다.
- 원천 모듈은 사용자 자산에서 수수료/공제를 수행하더라도, 반드시 별도 상태 전이로 **프로토콜 귀속 확정(settled-to-protocol)** 을 완료한 뒤에만 `RevenueEvent`를 발행한다 — [REFERENCE_REQUIRED].

### 2667.4 Validation
- Transfer 요청마다 `(source_vault_type, target_vault_type)` 매트릭스를 검증한다.
- 위반 시 즉시 거부한다.

### 2667.5 Failure handling
- ValidationFailure: 분리 규칙 위반.

### 2667.6 Audit
- 모든 이체 감사기록에 source/target vault type을 포함한다.

### 2667.7 Invariants
1. 사용자 자산은 분배 엔진의 입력 원천이 될 수 없다.
2. 보험 자산은 분배 엔진을 통해 Treasury로 이전될 수 없다.
3. DAO 수익은 정책에 의해 정의된 경로로만 귀속된다.


## 2668. Execution Authorization 매핑: 분배 카테고리별 권한 요구사항

### 2668.1 Purpose
분배 엔진이 수행하는 각 실행이 필요한 권한 범주(Authorization Category)를 일관되게 요구하도록 매핑을 고정한다.

### 2668.2 Architecture or Rule
1. Authorization Category 표준(Identity/Ownership/Object/Financial/NFT/Reserve/Liquidity/Treasury/DAO/Validator/Emergency/Regulatory)을 따른다.
2. 본 섹션에서 “Insurance Authorization” 및 “AuthorizationEnvelope/Capability” 상세는 [REFERENCE_REQUIRED]이며, 최소 계약만 고정한다.
   - `AuthorizationEnvelope`는 (caller, epoch/expiry, required_categories, capabilities) 검증 입력을 포함해야 한다 — [REFERENCE_REQUIRED].
3. 분배 엔진에서 요구되는 최소 권한은 다음과 같다.
   1) Distribution Settlement 실행자: Object Authorization + Financial Authorization  
   2) Treasury 라우트 포함 시: Treasury Authorization 추가  
   3) Insurance 라우트 포함 시: Insurance Authorization 추가 — [REFERENCE_REQUIRED]  
   4) 정책 변경/버전업: DAO Authorization (+ 필요 시 Validator Approval) — [REFERENCE_REQUIRED]  
   5) 비상 정지/동결 상태 해제: Emergency Authorization  
4. “Validator Consensus 확인”은 체인 합의(트랜잭션 최종화)를 의미하지 않는다. 이는 정책 변경 등 별도 승인 절차의 `validator_approved`와 같이 **거버넌스/승인 플래그**를 의미한다(2666.3).

### 2668.3 State/Flow
- 정산 트랜잭션은 `AuthorizationEnvelope`을 입력으로 받아, 라우트 구성에 따라 요구 권한을 계산한 후 통과 여부를 결정한다.

### 2668.4 Validation
- AuthorizationEnvelope 유효기간 만료(AuthorizationExpired) — [REFERENCE_REQUIRED]
- Capability 불일치(InvalidCapability) — [REFERENCE_REQUIRED]
- 호출자 불일치(UnauthorizedCaller) — [REFERENCE_REQUIRED]

### 2668.5 Failure handling
- AuthorizationFailure: 권한 누락 시 라우트 일부만 실행하는 것이 아니라 전체 정산이 실패한다(atomic).

### 2668.6 Audit
- `AuthorizationAuditRecord`: 요구 권한 목록, 제출된 증빙, 판정 결과 — [REFERENCE_REQUIRED].

### 2668.7 Invariants
1. Treasury/Insurance/DAO 관련 분배는 해당 권한 없이 실행 불가.
2. 비상 권한은 분배 비율 변경을 대체할 수 없다(권한 오남용 금지).
3. 승인 플래그(validator_approved)는 트랜잭션 최종성(Consensus)을 대체하지 않는다.


## 2669. 결정론적 정산(Deterministic Settlement) 및 반올림/잔액 처리 규칙

### 2669.1 Purpose
분배 결과의 결정론을 보장하고, 반올림으로 인한 잔액이 누적되어 임의로 사용되는 것을 방지한다.

### 2669.2 Architecture or Rule
- 분배 계산은 bps 기반 정수 연산으로 수행하며, **모든 라우트에 동일한 기본 반올림(Floor)** 을 적용한다(라우트별 rounding_mode는 본 장에서 제거하여 결정론과 합계 불변을 고정한다).
- 잔액(remainder)은 다음 중 하나로만 처리하며, 정책에 `remainder_rule`로 명시되어야 한다.
  1. `CarryToProtocolRevenueVault`: remainder는 `ProtocolRevenueVault`에 잔존 후 다음 epoch로 이월
  2. `AssignToRouteByPriority`: remainder를 **우선순위(priority) 오름차순**으로 순회하며 **1 단위씩**(최소 단위는 해당 자산의 on-chain 최소 단위) 배분하여 `remainder=0`이 될 때까지 할당
- 무정의 잔액(정책에 remainder_rule 부재)은 금지한다.

### 2669.3 State/Flow
1. `amount_i = floor(total * share_bps_i / 10000)` 산출
2. `remainder = total - Σ amount_i`
3. `remainder_rule` 적용
4. 최종 합계 재검증 후 실행

### 2669.4 Validation
- remainder 처리 후 `Σ amount_i + carried_amount == total`을 만족해야 한다(규칙에 따라 carried_amount는 0 또는 remainder).
- 음수/오버플로우 금지(checked arithmetic).
- `AssignToRouteByPriority`는 라우트 정렬이 결정론적이어야 한다(동일 priority 금지 또는 tie-breaker를 `route_type, target_ref`로 고정) — [REFERENCE_REQUIRED].

### 2669.5 Failure handling
- ValidationFailure: 합계 불일치, 산술 안전성 실패, 정렬 비결정론.

### 2669.6 Audit
- remainder 값, remainder_rule, `AssignToRouteByPriority` 사용 시 배분 결과를 기록한다.

### 2669.7 Invariants
1. 분배 합계 불변은 항상 유지된다.
2. remainder는 임의 주소로 송금될 수 없다(정책 기반 처리만 허용).


## 2670. 인터페이스 이벤트/감사 레코드 표준 및 외부(오프체인) 회계 연동 포인트

### 2670.1 Purpose
Treasury/Insurance/DAO 및 외부 회계/감사 시스템이 분배 결과를 재구성할 수 있도록, 이벤트/감사 레코드의 최소 표준 스키마를 정의한다.

### 2670.2 Architecture or Rule
- 분배 엔진은 다음 이벤트를 표준으로 발행한다.
  - `RevenueEventEmitted`
  - `DistributionSettled`
  - `TreasuryTransferApplied`
  - `InsuranceAccrued`
  - `PolicyUpdateProposed/Approved/Rejected`
- (불변성 모델 고정) 감사 레코드는 **append-only 이벤트**로 발행하며, 수정/삭제를 허용하지 않는다. 온체인 객체로 보관하는 구현을 선택하더라도, 해당 객체는 append-only 이벤트와 동등한 불변성을 가져야 한다 — [REFERENCE_REQUIRED].

### 2670.3 Object Model (Audit Record)
```move
public struct DistributionAuditRecord has store {
    audit_id: vector<u8>,       // tx_digest 기반 생성 가능(구현 선택)
    epoch: u64,
    policy_id: ID,
    policy_version: u64,
    source_type: u8,
    source_ref: ID,
    asset_type_tag: vector<u8>, // canonical TypeTag bytes
    total_generated: u64,
    route_results: vector<RouteResult>,
    authorized_by: vector<address>,
    executed_at: u64
}

public struct RouteResult has store {
    route_type: u8,
    target_ref: ID,
    amount: u64
}
```

### 2670.4 State/Flow
1. 정산 트랜잭션 종료 시 `DistributionAuditRecord` 이벤트 발행
2. 외부 인덱서(Indexer)는 epoch 및 policy_version으로 집계 가능
3. 외부 회계는 `audit_id` 및 `tx_digest`로 상호 검증 가능

### 2670.5 Validation
- 감사 레코드는 정산 실행과 동일 트랜잭션에서만 생성 가능(사후 조작 방지).
- 정책 버전, epoch, 총합 일치 검증.

### 2670.6 Failure handling
- AuditFailure: 감사 레코드 생성 실패 시 정산 트랜잭션 전체 실패(감사 누락 금지).

### 2670.7 Audit
- 본 섹션은 감사 표준 자체를 정의하므로, 감사 레코드의 삭제/변조는 불가(append-only 이벤트 기반 추적).

### 2670.8 Invariants
1. Audit-Completeness: 모든 정산은 감사 레코드를 반드시 동반한다.
2. Traceability: 원천 이벤트(source_ref)에서 Treasury/Insurance/DAO 귀속까지 역추적 가능하다.
3. Backward-Compatible: 새 route_type 추가 시 기존 필드 의미를 변경하지 않는다.
```

<-bash: cd: /home/boshin57/tobmate-agent-factory: No such file or SOURCE: workspace/drafts/3O_2671_2680_approved.md -->
```markdown
## 2671. Purpose

2671.1 본 절은 Gold Liquidity Pool Framework(GLPF)에서 오라클(Oracle), 한도(Limit), 비상정지(Emergency Halt)를 포함하는 위험관리 및 보호 규칙(Risk Controls)의 표준을 정의한다.

2671.2 목표는 다음을 동시에 만족하는 것이다.

1. 오라클 의존 작업의 실패-폐쇄(fail-closed) 보장
2. 풀/포지션 한도 및 자본 효율 파라미터(예: LTV, Concentration, Utilization Guardrail)의 상한/하한 강제
3. 비상정지 발동/해제의 실행 권한(Execution Authorization Framework, EAF) 및 검증(Business Rule Validation Framework, BRVF) 정형화
4. 어떤 유동성 작업도 준비금(Reserve), 원금 소유권(NFT Principal Ownership), 합의(Consensus), 감사(Audit) 불변식을 우회하지 못하도록 강제 지점(Enforcement Point) 명시
5. 검증 실패/권한 실패/합의 실패 시 상태 불변 유지 및 원자적 중단(Atomic Abort)

---

## 2672. Architecture or Rule

### 2672.1 Risk Control Plane 구성

2672.1.1 GLPF 위험관리 계층은 다음 객체와 정책 집합으로 구성된다.

- `RiskConfig` (global)
- `PoolRiskParams` (per pool)
- `PositionRiskState` (per position)
- `OracleState` (per oracle feed)
- `EmergencyHaltState` (global and/or per pool)
- `LimitLedger` (utilization 및 한도 소진량 추적)
- `ConsensusAttestation` (합의 증적)

2672.1.2 모든 유동성 관련 entry는 동일한 선행 단계를 강제한다.

1. EAF 권한 검증(Authorization Before Settlement)
2. BRVF 위험 규칙 검증(Validation Before Execution)
3. (필요 시) EAF의 Validator Authorization 및 합의 증적(Consensus Attestation) 검증(Consensus Before Finality)
4. 원자적 실행(Atomic Execution) 및 커밋
5. 이벤트/감사 레코드 기록 및 장기 보존(Long-Term Audit Preservation) (상세는 2676)

### 2672.2 객체 모델(Object Model)

#### 2672.2.1 `RiskConfig` (Global)

- `id: UID`
- `version: u64`
- `admin_policy_id: ID` (EAF 정책 식별자)
- `default_oracle_policy_id: ID` (오라클 업데이트 권한 정책)
- `default_emergency_policy_id: ID` (비상정지 권한 정책)
- `global_halt: bool`
- `risk_epoch: u64` (파라미터 적용 epoch)
- `default_conf_limit_bps: u64` (0~10000, 오라클 신뢰구간 상한 기본값)
- `audit_head_hash: vector<u8>` (감사 해시 체인 헤드; 2676.2 참조)

#### 2672.2.2 `PoolRiskParams` (Per Pool)

- `id: UID`
- `pool_id: ID`
- `status: u8`
  - `0=ACTIVE`, `1=HALTED`, `2=WITHDRAW_ONLY`, `3=DEPRECATED`
- `oracle_mode: u8`
  - `0=NONE`(오라클 미사용), `1=REQUIRED`(필수), `2=HYBRID`(제한적)
- `oracle_feed_ids: vector<ID>`
- `conf_limit_bps: u64` (0~10000, 0이면 `RiskConfig.default_conf_limit_bps` 적용)
- `max_tvl: u128` (총 예치 한도)
- `max_net_exposure: u128` (순 노출 한도; 2673.2.3 정의)
- `max_position_size: u128` (포지션 단일 한도)
- `max_leverage_bps: u64` (예: 30000 = 3.0x)
- `max_utilization_bps: u64` (0~10000)
- `max_concentration_bps: u64` (0~10000)
- `slippage_guard_bps: u64` (0~10000)
- `price_staleness_secs: u64`
- `circuit_breaker_bps: u64` (0~10000)
- `param_admin_policy_id: ID` (EAF)

#### 2672.2.3 `OracleState` (Per Feed)

- `id: UID`
- `feed_id: ID`
- `source_type: u8` (예: Pyth, Switchboard 등) [REFERENCE_REQUIRED]
- `last_price: u128` (정규화 가격; 단위는 feed 사양에 따르되 동일 feed 내 결정론 유지)
- `last_conf_bps: u64` (0~10000)
- `last_update_ts: u64`
- `status: u8`
  - `0=OK`, `1=STALE`, `2=DEVIATED`, `3=UNVERIFIED`, `4=HALTED`
- `attestation_ref: vector<u8>` (데이터 소스 서명/증적 참조)

#### 2672.2.4 `EmergencyHaltState`

- `id: UID`
- `scope: u8`
  - `0=GLOBAL`, `1=POOL`
- `scope_id: option<ID>` (POOL일 때 pool_id)
- `halt_reason_code: u64`
- `halted_at_ts: u64`
- `halted_by: address`
- `resume_ready: bool`
- `resume_after_ts: u64` (쿨다운)
- `emergency_policy_id: ID` (EAF)

#### 2672.2.5 `LimitLedger` (Per Pool)

- `id: UID`
- `pool_id: ID`
- `tvl_current: u128`
- `net_exposure_current: i128` (음수/양수 허용; 2673.2.3 정의)
- `utilization_bps: u64`
- `largest_position: u128`
- `topN_concentration_bps: u64` (0~10000; 2673.2.5 정의)
- `last_update_ts: u64`

#### 2672.2.6 `ConsensusAttestation` (Finality Required Operations)

- `epoch: u64`
- `scope: u8` (`0=GLOBAL`, `1=POOL`)
- `scope_id: option<ID>`
- `tx_digest: vector<u8>` (본 트랜잭션 다이제스트 바인딩)
- `quorum_sig_ref: vector<u8>` (정족수 서명/증적 참조)
- `nonce: u64` (재사용 방지)
- `issued_at_ts: u64`
- `expires_at_ts: u64`

---

## 2673. State/Flow

### 2673.1 유동성 작업 공통 실행 흐름(Enforcement Points)

2673.1.1 적용 대상 op_type(정규화)

- `ADD_LIQUIDITY`
- `REMOVE_LIQUIDITY`
- `SWAP`
- `OPEN_POSITION`
- `INCREASE_POSITION`
- `DECREASE_POSITION`
- `CLOSE_POSITION`
- `COLLECT_FEES`
- `REBALANCE`

2673.1.2 op_type 위험 분류(결정론)

- Risk-Increasing(위험 증가): `ADD_LIQUIDITY`, `SWAP`, `OPEN_POSITION`, `INCREASE_POSITION`, `REBALANCE`
- Risk-Reducing(위험 감소): `REMOVE_LIQUIDITY`, `DECREASE_POSITION`, `CLOSE_POSITION`, `COLLECT_FEES`

2673.1.3 공통 선행 게이트

1. **Halt Gate**
   - `RiskConfig.global_halt == false` AND
   - `PoolRiskParams.status in {ACTIVE, WITHDRAW_ONLY}` AND
   - 해당 스코프의 `EmergencyHaltState`가 활성 HALT가 아닐 것
2. **Authorization Gate (EAF)**
   - 호출자 및 관련 객체(LP/Position/Treasury 등)의 권한을 EAF 정책으로 검증
3. **Oracle Gate (조건부)**
   - 2673.3의 오라클 의존 매핑에 따라 오라클 검증을 통과해야 함
4. **Limit Gate**
   - 작업 후 상태가 `max_tvl`, `max_position_size`, `max_net_exposure`, `max_utilization_bps`, `max_concentration_bps`, `max_leverage_bps`를 초과하지 않을 것
5. **Consensus Gate (조건부)**
   - Finality Required Operations는 `ConsensusAttestation` 제출 및 검증을 통과해야 함(2674.1)
6. **Invariant Gate**
   - 준비금/소유권/감사/합의 불변식 우회 시도 차단(2673.4)

### 2673.2 한도(Limit) 및 가드레일 적용 규칙

2673.2.1 TVL 한도

- `tvl_current + delta_deposit <= max_tvl`
- 초과 시 실행 중단(Abort) 및 상태 롤백.

2673.2.2 포지션 한도

- `new_position_size <= max_position_size`
- 포지션 병합/증액도 동일 규칙 적용.

2673.2.3 순 노출(Net Exposure) 한도(결정론 정의)

- `net_exposure_current: i128`는 “풀의 위험자산 기준 순 노출”을 의미한다.
- 계산 단위: 풀의 기준 회계 단위(예: quote token 최소단위)로 정규화된 정수.
- 산정 입력:
  - `gross_long_value`(u128), `gross_short_value`(u128)를 동일 단위로 산정
  - `net_exposure = (gross_long_value as i128) - (gross_short_value as i128)`
- 가격 입력이 필요한 경우(가치 환산):
  - 오라클 의존으로 분류되며 2673.3의 fail-closed를 자동 상속한다.
- 한도 규칙:
  - `abs(net_exposure_after) <= max_net_exposure`
- 라운딩/오버플로:
  - 모든 곱/나눗셈은 u256 등 상위 정밀 정수로 중간 계산 후 하향 라운딩(floor)하여 u128/i128로 안전 캐스팅한다. 캐스팅 불가 시 Abort.

2673.2.4 이용률(Utilization) 한도(결정론 정의)

- `utilization_bps = floor( borrowed * 10000 / lendable )`, 단 `lendable > 0`.
- `borrowed`, `lendable`는 동일 토큰 최소단위(u128)로 표현한다.
- `lendable == 0`이면 `utilization_bps = 10000`으로 간주하여 위험 증가 동작을 금지한다.
- 규칙:
  - `utilization_bps_after <= max_utilization_bps`
- 오버플로:
  - `borrowed * 10000`은 상위 정밀 정수로 중간 계산 후 안전 캐스팅, 실패 시 Abort.

2673.2.5 집중도(Concentration) 가드레일(결정론 정의)

- `topN_concentration_bps = floor( topN_value * 10000 / total_value )`, 단 `total_value > 0`.
- `topN_value`는 상위 N개 포지션(또는 상위 N개 LP 기여분)의 가치 합으로 정의한다.
- N은 `PoolRiskParams`에 의해 고정된 상수로 취급되며, 본 절에서는 `N=5`를 기본으로 한다(변경은 파라미터 버전 업그레이드로만 허용).
- 가치 산정에 오라클이 필요한 경우 2673.3 fail-closed를 자동 상속한다.
- 규칙:
  - `topN_concentration_bps_after <= max_concentration_bps`
  - 단, Risk-Reducing op_type은 “집중도 감소 또는 불변”인 경우에 한하여 허용할 수 있으며, 허용 조건은 `topN_concentration_bps_after <= topN_concentration_bps_before`로 결정론적으로 판정한다.

2673.2.6 레버리지(Leverage) 한도(최소 정의)

- `leverage_bps = floor( position_notional * 10000 / position_equity )`, 단 `position_equity > 0`.
- `position_equity == 0`이면 위험 증가 동작을 금지한다.
- 가치 산정에 오라클이 필요한 경우 2673.3 fail-closed를 자동 상속한다.
- 규칙:
  - `leverage_bps_after <= max_leverage_bps`

### 2673.3 오라클(Oracle) 의존 시 검증 및 Fail-Closed

2673.3.1 오라클이 필요한 op_type 매핑(규범)

- `oracle_mode=NONE`: 모든 op_type은 오라클을 요구하지 않는다. 단, 오라클 입력을 사용하는 상태 전이는 금지된다.
- `oracle_mode=REQUIRED`: 다음 op_type은 오라클 검증을 요구한다.
  - `SWAP`, `OPEN_POSITION`, `INCREASE_POSITION`, `DECREASE_POSITION`, `CLOSE_POSITION`, `REBALANCE`
- `oracle_mode=HYBRID`: 다음 op_type은 오라클 검증을 요구한다.
  - `SWAP`, `OPEN_POSITION`, `INCREASE_POSITION`, `REBALANCE`
  - `DECREASE_POSITION`, `CLOSE_POSITION`은 오라클 검증 실패 시에도 “보수적 상한/하한 대체”가 가능할 때에만 제한적으로 허용(2673.3.4)

2673.3.2 오라클 검증 규칙(최소)

- `OracleState.status == OK`
- `now_ts - last_update_ts <= price_staleness_secs`
- `last_conf_bps <= effective_conf_limit_bps`
  - `effective_conf_limit_bps = (PoolRiskParams.conf_limit_bps != 0 ? PoolRiskParams.conf_limit_bps : RiskConfig.default_conf_limit_bps)`
- 가격 변동 제한(서킷브레이커):
  - `abs(last_price - ref_price) * 10000 / ref_price <= circuit_breaker_bps`, 단 `ref_price > 0`
  - `ref_price`는 “동일 feed의 직전 OK 가격(last_price_prev_ok)”로 정의한다. 직전 OK가 없으면 `UNVERIFIED`로 간주하여 fail-closed.
- 오버플로/0-division 발생 시 Abort.

2673.3.3 Fail-Closed 동작

- 2673.3.2 조건 중 하나라도 실패하면:
  - 가격 기반 상태 전이 금지
  - Risk-Increasing op_type은 **항상 거부**
  - `WITHDRAW_ONLY`에서는 2679.3에서 열거한 Risk-Reducing op_type만 허용 가능(정책화)

2673.3.4 오라클 결함 시 허용되는 예외(HYBRID에서만)

- 다음을 모두 만족할 때에만 Risk-Reducing op_type(`DECREASE_POSITION`, `CLOSE_POSITION`)을 허용할 수 있다.
  1. 가격 입력이 “사용자에게 불리한(보수적) 방향”으로 클램프(clamp)될 것
  2. 클램프 규칙은 파라미터로 고정되며(예: 담보가치는 0으로, 부채가치는 상한으로), 동적 외부 입력을 허용하지 않을 것
  3. 결과가 한도(Limit Gate)를 악화시키지 않을 것(2673.2.5의 감소/불변 조건 포함)

### 2673.4 “우회 금지” 강제 지점(Reserve/Ownership/Consensus/Audit)

2673.4.1 준비금(Verified Reserve) 우회 금지(규범 고정)

- GLPF는 FT/GOLDPEG의 발행·상환(issuance/redemption)을 직접 트리거하는 entry를 제공하지 않으며, 준비금 객체(Reserve Object)의 상태를 직접 변경하지 않는다.
- 예외적으로 “발행·상환과 결합된 설계”가 필요할 경우:
  - 반드시 GLPF 외부의 별도 모듈/명시적 entry로 분리되어야 하며,
  - EAF의 Reserve Authorization 및 BRVF의 준비금 상태 검증(Verified Reserve 선행)을 필수로 요구하고,
  - 검증 실패 시 원자적 중단(Atomic Abort)한다.
- 본 절의 GLPF op_type은 위 예외 경로를 포함하지 않는다.

2673.4.2 원금 소유권(NFT Principal Ownership) 우회 금지

- 어떤 유동성 작업도 Principal Ownership NFT의 소각/이전/잠금 상태 변경을 “암묵적으로” 수행할 수 없다.
- NFT 상태 변경이 필요한 경우:
  - 별도 명시 동작으로 분리
  - EAF의 NFT Authorization을 요구
  - BRVF에서 “원금 소유권 비침해” 조건을 검증

2673.4.3 합의(Consensus) 우회 금지(본 절 내 최소 메커니즘 고정)

- Finality Required Operations는 `ConsensusAttestation` 제출을 요구하며, 다음 중 하나를 만족해야 한다.
  1. EAF의 Validator Authorization으로 호출이 승인되고, BRVF가 `ConsensusAttestation`의 epoch/정족수/만료/재사용 방지를 검증한다.
  2. 또는, DAO/운영 정책이 “합의 불요”로 명시한 제한 범위 내 동작(예: 단일 사용자 Risk-Reducing)인 경우에만 Consensus Gate를 생략할 수 있다(정책 식별자는 `admin_policy_id`로 고정 관리).
- Finality Required Operations의 최소 집합:
  - `set_pool_risk_params`
  - `trigger_emergency_halt`(GLOBAL 또는 시스템 영향 범위)
  - `resume_from_halt`(GLOBAL 또는 시스템 영향 범위)

2673.4.4 감사(Audit) 우회 금지

- 모든 위험 파라미터 변경, HALT 발동/해제, 오라클 상태 전이는 표준 이벤트 및 감사 레코드(2676.2)를 생성해야 한다.
- 감사 레코드 갱신이 실패하거나 결정론적 해시 체인 갱신이 불가능하면 커밋을 금지한다(원자적 중단).

---

## 2674. Validation

### 2674.1 BRVF 검증 항목(최소 집합)

- `RiskConfig.version` 및 `PoolRiskParams.version` 정합성
- Halt Gate 조건
- Oracle Gate 조건(해당 시)
- Limit Gate 조건
- 슬리피지 가드레일(`slippage_guard_bps`) 충족
- 상태 머신 합법성(예: `HALTED` 상태에서 Risk-Increasing op_type 불가)
- 재진입/리플레이 방지:
  - `tx_digest` 바인딩(감사 레코드 및 합의 증적에 포함)
  - `ConsensusAttestation.nonce`의 재사용 금지(스코프별 nonce 레저는 구현 객체로 유지되어야 함) [REFERENCE_REQUIRED]
- 합의 증적 검증(해당 시):
  - `now_ts <= expires_at_ts`
  - `tx_digest == 현재 트랜잭션 다이제스트`
  - `epoch == RiskConfig.risk_epoch` 또는 정책이 허용하는 범위 내
  - `quorum_sig_ref`가 EAF의 Validator Authorization 정책에 부합함(정족수 서명 검증 방식은 정책에 의해 고정)

### 2674.2 EAF 권한 요구(최소 집합)

- `set_pool_risk_params`: Treasury Authorization 또는 DAO Authorization(정책에 따름) + (Finality Required 시) Validator Authorization
- `trigger_emergency_halt`: Emergency Authorization + (Finality Required 시) Validator Authorization
- `resume_from_halt`: Emergency Authorization + (필요 시) DAO Authorization(2단 승인) + (Finality Required 시) Validator Authorization
- `update_oracle_state`:
  - Oracle Authority(데이터 소스 서명/증적 제출) + 정책에 따라 Validator Authorization(합의 증적 요구 여부는 feed 중요도/범위에 의해 결정)

오류 코드는 EAF/BRVF 표준을 따른다(예: `E1002 Unauthorized Caller`, `E1007 Business Rule Violation`, `E1008 Invalid Object State`).

---

## 2675. Failure handling

### 2675.1 공통 실패 처리 원칙

- 실패 시 **원자적 중단(Atomic Abort)**으로 커밋 전 상태를 유지한다.
- 실패는 “부분 체결/부분 정산”을 남기지 않는다(Deterministic State Transition).

### 2675.2 실패 유형별 처리

1. **검증 실패(BRVF)**
   - `E1007` 또는 규칙별 세부 코드로 중단
   - `LimitLedger` 및 포지션/풀 상태 변경 없음
2. **권한 실패(EAF)**
   - `E1002/E1003/E1004`로 중단
   - 상태 변경 없음
3. **오라클 실패**
   - `STALE/DEVIATED/UNVERIFIED/HALTED`면 fail-closed
   - Risk-Increasing op_type 금지
4. **합의 실패/미확인**
   - Finality Required Operations를 중단
   - 상태 변경 없음
5. **비상정지 상태에서의 금지 동작**
   - `PoolRiskParams.status` 또는 `EmergencyHaltState`에 의해 즉시 중단
   - `WITHDRAW_ONLY/HALTED`의 허용 동작만 통과(2679.3)

---

## 2676. Audit

### 2676.1 표준 이벤트(Event) (성공 커밋에 한정)

- `RiskParamsUpdated`
  - `pool_id, old_hash, new_hash, updated_by, ts, version`
- `EmergencyHaltTriggered`
  - `scope, scope_id, reason_code, by, ts`
- `EmergencyHaltResumed`
  - `scope, scope_id, by, ts, cooldown_satisfied: bool`
- `OracleStatusChanged`
  - `feed_id, old_status, new_status, last_price, ts`
- `ConsensusAttestationConsumed`
  - `scope, scope_id, epoch, nonce, tx_digest, ts`

2676.1.1 실패(Abort)된 트랜잭션에 대해 온체인 이벤트는 기록되지 않는다. 한도 초과 시도 등 “거부 로그”는 표준 오류코드 및 트랜잭션 시뮬레이션/실행 로그로 대체한다.

### 2676.2 감사 레코드(Audit Record) 최소 스키마(본 절 내 고정)

- `AuditRecord`
  - `tx_digest: vector<u8>`
  - `caller: address`
  - `object_ids: vector<ID>` (변경된/참조된 주요 객체)
  - `policy_ids: vector<ID>` (적용된 EAF 정책 식별자)
  - `brvf_version: u64`
  - `eaf_policy_version: u64` [REFERENCE_REQUIRED]
  - `event_type: u64` (정규화 코드)
  - `event_hash: vector<u8>` (결정론적 해시)
  - `prev_event_hash: vector<u8>` (해시 체인)
  - `ts: u64`

2676.2.1 해시 체인 갱신 규칙(결정론)

- `event_hash = H(tx_digest || caller || object_ids || policy_ids || brvf_version || event_type || ts || prev_event_hash)`
- `RiskConfig.audit_head_hash`는 커밋 시 `event_hash`로 갱신한다.
- 해시 함수 및 직렬화 규약은 프로토콜 전역 표준을 따른다. 해당 표준이 아직 고정되지 않은 경우, 본 절에서는 `H`를 “결정론적 암호학적 해시”로 정의하고 구현 표준은 상위 규격으로 위임한다. [REFERENCE_REQUIRED]
- `audit_head_hash` 갱신이 실패하면 커밋을 금지한다.

### 2676.3 장기 보존(Long-Term Audit Preservation)

- 감사 레코드는 객체 수명 종료(풀 DEPRECATED 포함) 이후에도 조회 가능해야 한다.
- 삭제/덮어쓰기 금지(append-only) 성질을 유지해야 한다.
- 조회 경로(인덱싱/보관 객체 구조)는 구현에 위임하되, 최소로 `tx_digest`와 `object_id` 기반 조회가 가능해야 한다. [REFERENCE_REQUIRED]

---

## 2677. Invariants

2677.1 **Fail-Closed Oracle Invariant**  
오라클이 요구되는 op_type에서 오라클 검증이 실패하면, Risk-Increasing 상태 전이는 발생하지 않는다.

2677.2 **Limit Preservation Invariant**  
어떤 커밋된 상태에서도 `LimitLedger`의 지표는 `PoolRiskParams`의 상한을 초과하지 않는다.

2677.3 **Emergency Halt Determinism Invariant**  
`HALTED/WITHDRAW_ONLY` 상태에서 허용된 op_type 집합은 2673.1.1~2673.1.2 및 2679.3에 의해 결정론적으로 평가되며, 동일 입력에 대해 동일 결과를 산출한다.

2677.4 **No Bypass Invariant (Reserve/Ownership/Consensus/Audit)**  
유동성 관련 entry는 준비금/원금 소유권/합의/감사 불변식을 우회하는 상태 전이를 커밋할 수 없다.

---

## 2678. 풀/포지션 한도 및 자본 효율 파라미터 가드레일(구체 규칙)

### 2678.1 파라미터 분류

- **Hard Limits(하드 한도)**: `max_tvl`, `max_position_size`, `max_net_exposure`
- **Efficiency Guardrails(효율 가드레일)**: `max_utilization_bps`, `max_concentration_bps`, `slippage_guard_bps`, `max_leverage_bps`
- **Oracle Safety(오라클 안전)**: `price_staleness_secs`, `circuit_breaker_bps`, `conf_limit_bps`

### 2678.2 업데이트 절차(Param Change Flow)

1. EAF로 `param_admin_policy_id` 검증
2. (Finality Required 시) Validator Authorization 및 `ConsensusAttestation` 제출
3. BRVF로 버전/범위/상호 제약 검증
4. `RiskParamsUpdated` 이벤트 및 `AuditRecord` 기록
5. 커밋

### 2678.3 상호 제약(Constraint) 예시(최소)

- `0 < max_tvl`
- `0 < max_position_size <= max_tvl`
- `0 <= max_utilization_bps <= 10000`
- `0 <= max_concentration_bps <= 10000`
- `0 <= slippage_guard_bps <= 10000`
- `0 < max_leverage_bps`
- `price_staleness_secs > 0`
- `0 <= conf_limit_bps <= 10000`
- `0 <= circuit_breaker_bps <= 10000`

---

## 2679. 비상정지(Emergency Halt)

### 2679.1 트리거 조건(Trigger Conditions)

- 오라클 상태가 `HALTED/UNVERIFIED`로 전이
- `LimitLedger`가 상한을 위반하려는 시도가 반복적으로 관측되는 경우(정의된 관측 규칙/윈도우는 정책으로 고정) [REFERENCE_REQUIRED]
- 비정상 거래/가격 급변이 `circuit_breaker_bps`를 반복 위반
- 감사/합의/권한 검증 계층 장애 감지 [REFERENCE_REQUIRED]
- 규제/정책 기반 정지(Regulatory Halt) [REFERENCE_REQUIRED]

### 2679.2 발동 권한(Authorization)

- `trigger_emergency_halt`는 EAF의 Emergency Authorization을 요구한다.
- 스코프가 GLOBAL이면 `RiskConfig.admin_policy_id` 또는 `default_emergency_policy_id`를 따른다.
- 스코프가 POOL이면 `PoolRiskParams.param_admin_policy_id` 또는 지정된 `EmergencyHaltState.emergency_policy_id`를 따른다.
- GLOBAL 영향 또는 시스템 위험 상태로 분류되는 경우, Validator Authorization 및 `ConsensusAttestation`을 추가로 요구할 수 있다(정책화).

### 2679.3 정지 시 허용 동작(Allowed Operations) (명시 열거)

- `HALTED`:
  - 허용: `REMOVE_LIQUIDITY`, `DECREASE_POSITION`, `CLOSE_POSITION`, `COLLECT_FEES`
  - 금지: `ADD_LIQUIDITY`, `SWAP`, `OPEN_POSITION`, `INCREASE_POSITION`, `REBALANCE`
- `WITHDRAW_ONLY`:
  - 허용: `REMOVE_LIQUIDITY`, `DECREASE_POSITION`, `CLOSE_POSITION`, `COLLECT_FEES`
  - 금지: `ADD_LIQUIDITY`, `SWAP`, `OPEN_POSITION`, `INCREASE_POSITION`, `REBALANCE`

2679.3.1 신규 op_type 추가 시 역호환(Constitutional Sustainability)

- 신규 op_type은 반드시 2673.1.2의 위험 분류 규칙에 포함되어야 하며,
- `HALTED/WITHDRAW_ONLY`에서 기본값은 “금지(deny-by-default)”로 평가되어야 한다.
- 허용으로 전환하려면 파라미터 버전 업그레이드 및 감사 레코드가 수반되어야 한다.

### 2679.4 재개 절차(Resume Flow)

1. 쿨다운 확인: `now_ts >= resume_after_ts`
2. 오라클/한도/시스템 정상성 체크(BRVF)
3. EAF로 `resume_from_halt` 권한 확인(단독 또는 다중승인)
4. (Finality Required 시) Validator Authorization 및 `ConsensusAttestation` 검증
5. `EmergencyHaltResumed` 이벤트 및 `AuditRecord` 기록
6. `PoolRiskParams.status -> ACTIVE` 또는 `RiskConfig.global_halt=false`
7. 커밋

---

## 2680. 실패 처리 및 불변 유지(종합)

2680.1 본 절의 모든 규칙은 “Integrity Above Convenience”를 따른다. 즉, 편의적 완화보다 무결성 보존을 우선하며, 오라클/권한/검증/합의 중 어느 하나라도 실패하면 실행은 중단된다.

2680.2 구현 강제 지점은 “entry 함수 선행 게이트 + 상태 머신 제한 + 감사 레코드/해시 체인 갱신 실패 시 커밋 금지”의 조합으로 구성되며, 이를 통해 다음이 유지된다.

- 검증 실패: 상태 불변
- 권한 실패: 상태 불변
- 합의 실패: Finality 불발 및 상태 불변
- 감사 실패: 커밋 금지 및 상태 불변

2680.3 본 절은 Chapter 3N에서 확립된 준비금/소유권/실행권한/감사/합의의 헌법적 보증을 변경하지 않으며, GLPF의 위험관리 계층은 해당 보증을 우회할 수 없는 방식으로만 확장된다.
```

<-bash: cd: /home/boshin57/tobmate-agent-factory: No such file or SOURCE: workspace/drafts/3O_2681_2690_approved.md -->
## 2681. 감사·컴플라이언스(Audit & Compliance) 및 결정론(Determinism) 보장 — 개요

### Purpose
본 절은 GLPF(Gold Liquidity Pool Framework)의 모든 유동성 관련 상태 전이(풀 생성/예치/회수/스왑/수수료 분배)가 (1) 불변 감사(Immutable Audit)와 합의 커밋(Consensus Commit)에 의해 최종 확정되고, (2) 동일 입력에 대해 동일 결과를 재현하는 결정론(Determinism)을 유지하며, (3) 준비금·보관기관·거래사유에 대한 컴플라이언스 태깅(Compliance Tagging)을 통해 규제·기관 감사 요구를 충족하도록 하는 구현 규격을 정의한다.

### Architecture or Rule
1. GLPF의 모든 상태 전이는 **감사 이벤트(Audit Event) 기록 → 합의 커밋 바인딩(Consensus Commit Binding) → 상태 스냅샷 갱신**의 순서를 강제한다.
2. 감사 이벤트는 **고정 이벤트 스키마(Fixed Event Schema)**를 사용하며, 스키마는 업그레이드 시에도 후방 호환(backward compatibility)을 유지한다(필드 추가는 가능하되 의미 변경 금지).
3. 컴플라이언스 태그는 **준비금 ID(reserve_id), 보관기관 ID(custodian_id), 거래사유 코드(reason_code)**를 최소 포함하며, 트랜잭션 단위로 감사 이벤트에 포함되어 봉인(seal)된다.
4. 결정론 검증은 **스냅샷/리플레이(snapshot/replay)**로 수행 가능해야 하며, 리플레이는 동일 입력(2682의 총순서 이벤트 스트림, 동일 기준 스냅샷, 동일 버전 규칙)을 사용하여 동일 최종 상태를 산출해야 한다.
5. 장기 보존(Long-Term Audit Preservation)은 **이벤트 본문(온체인) + 외부 증빙 해시(merkle root / document hash)**를 결합하며, 외부 저장소 교체에도 무결성 검증이 가능해야 한다.
6. 실패 트랜잭션은 “미기록”이 허용되지 않는다. 모든 실패는 동일한 고정 스키마 하에서 `REJECTED` 또는 `FAILED` 유형의 감사 이벤트로 기록되며, 최소한 `reject_code`, `failed_gate(A/B/C/D)`, `cause_hash(선택)`를 포함한다. 단, 사용자 UI/인덱서가 “노출 이벤트를 필터링”하는 것은 허용되나, 감사 스트림의 기록 자체는 생략될 수 없다.

### State/Flow
- 공통 실행 흐름(모든 GLPF 액션에 적용):
  1) Business Rule Validation (Gate A)  
  2) Execution Authorization (Gate B)  
  3) State Transition 계산(결정론)  
  4) Audit Event 기록(고정 스키마, 총순서, 컴플라이언스 포함) (Gate C)  
  5) Consensus Commit Binding 생성 및 검증(합의 증명 결합) (Gate D)  
  6) Canonical State 확정 및 Snapshot 갱신  

### Validation
- 아래 조건 중 하나라도 실패하면 상태 전이는 중단되며(Execution Stops), **반드시 `REJECTED`/`FAILED` 감사 이벤트가 기록**되어야 한다(2682의 총순서에 포함).
  - 스키마 버전 불일치
  - 필수 컴플라이언스 태그 누락
  - 감사 기록 총순서 규칙 위반(커밋/트랜잭션/이벤트 인덱스 불일치)
  - 합의 커밋 바인딩 검증 실패(커밋 참조 누락/불일치 포함)
  - 비결정적 입력(시간, 랜덤, 비정렬 컬렉션 등) 사용 탐지
- `REJECTED`/`FAILED` 이벤트는 “상태 변경 없음”을 명시하는 `pre_state_hash == post_state_hash`를 기본 규칙으로 한다(예외가 필요한 경우는 명시적으로 금지 또는 별도 타입으로 분리).

### Failure handling
- 실패 유형:
  - **ValidationFailure**: 규칙 위반. 상태 변경 없음. `REJECTED` 기록.
  - **AuthorizationFailure**: 권한 위반. 상태 변경 없음. `REJECTED` 기록.
  - **CommitFailure**: 합의 커밋 바인딩 실패. **이벤트는 폐기 금지**, `FAILED` 또는 `UNFINALIZED`로 기록하고 “비확정 구간”으로 봉인한다(2683 참조).
  - **SchemaFailure**: 이벤트 스키마/총순서 규칙 위반. 상태 변경 없음. `FAILED` 기록.
- 실패 시 공통 처리:
  - 상태는 이전 스냅샷으로 유지
  - 트랜잭션 결과에 `reject_code` 및 최소 메타데이터 반환
  - 실패 감사 이벤트는 동일 스트림에 기록하되, 조회 기본값은 `Finalized=true`만 반환하도록 분리 필터링한다.

### Audit
- 감사는 “행위(action) 단위”가 아니라 “상태 전이(state transition) 단위”로 기록한다.
- 모든 감사 이벤트는 다음을 포함한다:
  - 상태 전이 전/후의 핵심 수치(예: 풀 잔액, LP 총량, 누적 수수료, 가격 상태)
  - 입력 파라미터(정규화된 형태 또는 `payload_hash`)
  - 컴플라이언스 태그
  - 합의 커밋 바인딩 참조(블록/체크포인트/커밋 해시 등)
  - Gate A/B 결과의 재현 가능한 참조(예: `validation_result_hash`, `authorization_proof_ref`, `policy_ref`)

### Invariants
본 절은 외부 레지스트리 문서에 대한 교차참조 없이, GLPF 감사/결정론 레이어의 최소 불변식을 다음과 같이 자체 정의한다.
1. **결정론 불변식**: 동일한 기준 스냅샷과 동일한 Finalized 이벤트 총순서 입력은 동일 `state_hash`를 산출해야 한다.
2. **합의-최종성 불변식**: 합의 커밋 바인딩 없이 `Finalized=true`인 이벤트는 존재할 수 없다.
3. **감사-연속성 불변식**: 이벤트 시퀀스는 총순서 인덱스가 단조 증가하며, 어떠한 이벤트도 삭제/재정렬될 수 없다(필요 시 Tombstone으로만 대체).
4. **감사-무결성 불변식**: `commit_hash`–`event_root`–`event_body_hash`의 3자 검증이 항상 가능해야 하며, 불일치가 발견되면 해당 범위는 Canonical State로 채택될 수 없다.
5. **준비금 우회 금지 불변식**: 어떤 유동성 연산도 준비금/감사/동결 상태 제약을 우회할 수 없다(헌법 1,4,5,9,6,10의 방향과 합치).

---

## 2682. Audit Recording 순서 고정 및 이벤트 스키마(Event Schema)

### Purpose
풀/스왑/예치/회수/분배에 대한 감사 기록의 **순서(order)**와 **스키마(schema)**를 고정하여, 리플레이 가능성과 장기 감사를 보장한다.

### Architecture or Rule
1. GLPF 이벤트는 **총순서(total order)**를 가지며, 총순서는 다음 튜플의 사전식 순서로 정의한다.  
   - `(commit_epoch, commit_id, tx_index, event_index)`
2. 이벤트 기록 순서는 트랜잭션 범위에서 다음을 강제한다.
   - `PreStateSnapshot` → `ActionEvent|RejectedEvent|FailedEvent` → `PostStateSnapshot` → `CommitBinding`
3. 이벤트 스키마는 다음 공통 헤더를 가진다(모든 이벤트 공통):
   - `schema_id`(고정), `schema_version`(증가형), `event_type`, `event_id`, `commit_epoch`, `commit_id`, `tx_id`, `tx_index`, `event_index`, `actor`, `protocol_version`
   - `compliance`(2685에서 정의)
   - `commit_ref`(2683에서 바인딩)
4. `commit_epoch` 및 그로부터 파생되는 모든 “시간성 필드”는 **합의 계층이 제공하는 커밋/블록/체크포인트 메타데이터에서만 파생**되어야 하며, 트랜잭션 실행 중 노드가 wall-clock 기반으로 임의 생성하는 것을 금지한다. `PreStateSnapshot/ActionEvent/PostStateSnapshot` 모두 동일 규칙을 적용한다.

### State/Flow
- Action별 이벤트 타입(최소):
  - `POOL_CREATED`
  - `LIQUIDITY_DEPOSITED`
  - `LIQUIDITY_WITHDRAWN`
  - `SWAP_EXECUTED`
  - `FEE_DISTRIBUTED`
  - `REJECTED`
  - `FAILED`
- 각 타입은 트랜잭션 내 `event_index`로 유일하게 식별되며, 파생 계산은 `PostStateSnapshot`에 반영한다.

### Validation
- `PreStateSnapshot.state_hash`는 직전 커밋 기준의 해당 풀 상태 해시와 일치해야 한다(연속성).
- `ActionEvent`의 파라미터는 정규화(canonical encoding)되어야 한다(키 정렬, 고정 소수점/정수 단위, 주소 표준화).
- `PostStateSnapshot`은 `PreStateSnapshot + (ActionEvent|RejectedEvent|FailedEvent)`로부터 결정론적으로 계산 가능해야 한다.
- `RejectedEvent/FailedEvent`는 기본적으로 `pre_state_hash == post_state_hash`를 만족해야 한다.

### Failure handling
- 총순서/연속성 불일치 시 `SchemaFailure`로 처리하고 커밋 불가. 단, 커밋 실패로 전이되는 경우에도 2681/2683 규칙에 따라 `FAILED/UNFINALIZED`로 기록되어야 한다.

### Audit
- 스키마는 “의미 안정성(semantic stability)”을 요구한다.
  - 필드 의미 변경 금지
  - 기존 필드 삭제 금지
  - 신규 필드 추가는 `schema_version` 증가로만 허용

### Invariants
- “No Ledger Divergence”를 위해 이벤트 직렬화(canonical serialization) 규칙과 총순서 튜플 산출 규칙이 모든 노드에서 동일해야 한다.

---

## 2683. 불변 감사(Immutable Audit)와 합의 커밋(Consensus Commit) 연결

### Purpose
감사 이벤트가 “기록되었다”는 사실만으로는 부족하므로, **합의 커밋에 의해 Finalized된 감사**만을 정식 감사 원장으로 인정하는 결합 규칙을 정의한다.

### Architecture or Rule
1. `CommitBinding` 이벤트는 다음을 포함한다.
   - `commit_type`(block/checkpoint 등)
   - `commit_id`(높이/시퀀스)
   - `commit_hash`
   - `commit_epoch`
   - `event_root`(해당 커밋 내 이벤트들의 Merkle root 또는 등가의 검증 가능한 루트)
2. 감사 이벤트는 `commit_ref`가 유효하게 결합되기 전까지 `Finalized=false` 상태로 간주한다.
3. `Finalized=true`로 승격되는 조건:
   - `commit_hash`가 합의 규칙에 의해 확정(finality)되었음
   - `event_root` 검증 성공
   - `tx_id` 및 `event_index` 포함 관계가 커밋에 의해 증명됨
4. **CommitFailure 처리 불변 규칙**:
   - `ActionEvent`의 “폐기(discard)”는 금지한다.
   - 커밋 바인딩이 생성/검증되지 못한 경우, 동일 총순서 위치에 `FAILED` 또는 `UNFINALIZED` 사건을 나타내는 이벤트(또는 Tombstone 이벤트)를 기록하여 연속성을 유지하고, 해당 범위를 “비확정 구간(unfinalized range)”으로 봉인(seal)한다.

### State/Flow
- 정상 흐름: `ActionEvent` 기록 → `CommitBinding` 생성 → 검증 성공 → `Finalized=true`
- 비정상 흐름(커밋 바인딩 실패): `ActionEvent`(또는 `FAILED/UNFINALIZED` 이벤트) 기록 → `CommitBinding` 미성립 → 해당 이벤트는 `Finalized=false`로 유지되며, 리플레이/정산/외부 보고에서 “정식 원장”으로 취급될 수 없다.

### Validation
- `commit_hash` ↔ `event_root` 상호 검증 필수.
- 커밋 참조는 체인 외부에서 임의 주입될 수 없으며, 합의 계층이 제공하는 증명만 허용한다.

### Failure handling
- `CommitFailure`:
  - 상태 확정(Canonical State 반영) 금지
  - 이벤트는 `Finalized=false`로 유지하되, 총순서/연속성 유지를 위해 Tombstone 또는 `UNFINALIZED` 표기를 포함한다.
  - 재처리(retry)가 가능한 체인 설계라면, 재처리 결과는 “추가 이벤트”로만 기록되며 기존 이벤트를 수정/삭제하지 않는다.

### Audit
- 감사 조회 시 기본 필터는 `Finalized=true`만 반환한다.
- `Finalized=false` 이벤트는 규제/분쟁 대응 목적의 보존은 가능하나, “정식 원장”으로 표현하면 안 된다.

### Invariants
- 합의 없이 Finality 불가.
- Finalized 이벤트는 변경/삭제 불가(불변 감사).

---

## 2684. 상태 스냅샷/리플레이(Replay)로 결정론 검증

### Purpose
외부 감사자·기관·노드가 동일 결과를 재현함으로써 GLPF의 결정론과 감사 무결성을 독립적으로 검증할 수 있도록 한다.

### Architecture or Rule
1. 스냅샷은 최소 다음을 포함한다.
   - `snapshot_id`, `snapshot_epoch(=commit_epoch)`, `state_hash`
   - 풀별 핵심 상태(잔액, LP 공급량, 수수료 누적, 가격 상태 등)
   - `protocol_version`, `schema_version_set`
2. 리플레이 입력은 다음 3요소로 구성된다.
   - 기준 스냅샷(시점 t)
   - t 이후의 Finalized 이벤트 스트림(2682의 총순서)
   - 동일 버전의 실행 규칙(Deterministic Upgrade 전제)
3. 리플레이 결과의 `state_hash`는 온체인 `PostStateSnapshot.state_hash`와 일치해야 한다.

### State/Flow
- 노드는 주기적으로 스냅샷을 생성하며(정책 기반), 스냅샷 간 구간은 이벤트 스트림으로 복원 가능해야 한다.
- 감사자는 임의 구간을 선택하여 리플레이 검증을 수행할 수 있다.

### Validation
- 비결정성 금지 항목(예시):
  - wall-clock time 직접 사용 금지(합의 커밋의 epoch만 허용)
  - RNG 사용 금지(필요 시 합의에 포함된 seed만 사용)
  - map/set 순회 시 정렬 없는 반복 금지
  - 부동소수점 사용 금지(고정 정수 단위 사용)

### Failure handling
- 리플레이 불일치 발생 시:
  - 해당 구간의 커밋/이벤트 루트/정규화 규칙을 재검증
  - 불일치가 재현되면 “결정론 위반 사건(Determinism Incident)”으로 분류하고, 원인 트랜잭션 범위를 격리한다.

### Audit
- 리플레이 검증 결과는 별도 “검증 리포트 해시(report_hash)”로 보존할 수 있으며, 필요 시 온체인 참조를 추가한다(문서 본문은 해시 기반 외부 보관).

### Invariants
- Canonical ledger state의 결정론 유지.

---

## 2685. 컴플라이언스 태깅(Compliance Tagging): reserve_id, custodian_id, reason_code

### Purpose
GLPF 상의 유동성·거래 행위를 준비금 및 보관기관 맥락에 연결하여, 규제 준수(Compliance) 및 기관 감사 요구를 충족한다.

### Architecture or Rule
1. 모든 GLPF `ActionEvent`는 `compliance` 필드를 포함한다.
2. `compliance` 최소 필드:
   - `reserve_id: ID` (준비금 객체 참조)
   - `custodian_id: ID` (보관기관 참조; **행위 시점 기준으로 고정 기록**)
   - `reason_code: u32` (거래 사유 코드)
   - `custodian_effective_epoch: u64` (선택 필드가 아니라 **권고 필수 필드**로 취급; 최소한 `commit_epoch`와 함께 “당시 custodian” 해석이 가능해야 함)
3. 확장 필드(선택):
   - `jurisdiction_code: u16`
   - `kyc_tier: u8`
   - `sanctions_screening_ref: vector<u8>`(해시)
   - `policy_ref: vector<u8>`(적용 정책 버전/해시)

### State/Flow
- 풀 생성 시 `reserve_id`가 고정 바인딩되며, 이후 스왑/예치/회수/분배 이벤트는 해당 풀의 `reserve_id`를 상속한다.
- `custodian_id`는 `reserve_id`로부터 도출될 수 있으나, 장기 감사에서 참조 단절/변경 혼동을 방지하기 위해 이벤트에 **명시적으로 포함**한다.
- 보관기관 변경(Custodian change)이 발생하는 경우, 변경이 커밋된 `commit_epoch`를 기준으로 “이전 이벤트의 custodian_id는 당시 값으로 유지”되며 재기록/수정이 금지된다.

### Validation
- `reserve_id` 사용 가능성(모든 GLPF 액션: 풀 생성/예치/스왑/회수/분배에 공통 적용):
  1) 준비금은 **검증된 상태(Verified/Active 등)** 여야 한다.
  2) 준비금은 **동결(Frozen) 상태가 아니어야 한다**.
  3) 준비금에 연결된 감사(Reserve Audit)는 **Active이며 만료(Expired)되지 않아야 한다**. 또한 Failed/Discrepancy/Expired에 준하는 상태는 즉시 거부되어야 한다.
  4) 위 조건 중 하나라도 위반 시 `reject_code=COMPLIANCE_RESERVE_NOT_ELIGIBLE`(또는 동등 코드)로 거부하고, `REJECTED` 감사 이벤트에 원인(`cause_hash` 또는 세부 코드)을 포함한다.
- `reason_code`:
  - 사전 정의된 코드 집합에 속해야 하며, 미정의 코드는 거부한다.
- 태그와 실제 실행 내용 불일치(예: 풀의 reserve와 상이한 reserve_id 태깅) 시 `ValidationFailure`.

### Failure handling
- 태그 누락/오류는 “컴플라이언스 실패”로 분류하고 실행 중단.
- 반복 위반 주체의 제한은 거버넌스 정책에 의해 수행되나, 본 절에서는 구체 거버넌스 절을 인용하지 않으며 [REFERENCE_REQUIRED]로 남긴다.

### Audit
- 감사자는 이벤트 스트림을 `reserve_id`, `custodian_id`, `reason_code`로 필터링하여 “준비금 단위 전 구간 추적(end-to-end traceability)”을 수행할 수 있어야 한다.

### Invariants
- 준비금 검증 및 소유권/합의/감사 불변식은 GLPF 태그를 통해 우회될 수 없다.

---

## 2686. 장기 보존(Long-Term Audit Preservation) 규칙

### Purpose
수십 년 단위의 운영을 전제로, 구현·저장소·버전이 변경되더라도 감사 기록의 무결성과 재검증 가능성을 유지한다.

### Architecture or Rule
1. 온체인에는 다음만을 영구 보존한다.
   - 이벤트 본문(고정 스키마)
   - 스냅샷 해시(state_hash)
   - 외부 증빙 참조의 해시(`evidence_root` 또는 `document_hash`)
2. 외부 저장은 교체 가능하나, 교체 시에도 동일 해시로 무결성을 검증할 수 있어야 한다.
3. 감사 데이터는 “읽기 호환성(read compatibility)”을 최우선으로 하며, 과거 이벤트는 새로운 노드에서도 해석 가능해야 한다.

### State/Flow
- 감사 자료(예: 보고서 PDF, 거래 근거 문서, 기관 확인서)는 외부 저장소에 보관하고, 온체인 이벤트에는 해시 및 최소 메타데이터만 기록한다.

### Validation
- 외부 자료 제출/갱신 시:
  - 해시 불일치 금지
  - 제출 주체 서명 및 권한 검증
  - 스키마 버전 정책 준수

### Failure handling
- 외부 저장소 장애는 “자료 접근성” 문제로 분리 처리하되, 온체인 무결성(해시)은 유지되어야 한다.
- 해시 불일치는 “증빙 위조/손상”으로 분류하여 감사 경보를 생성한다.

### Audit
- 장기 감사는 “온체인 이벤트 + 커밋 바인딩 + 외부 증빙 해시”의 3요소로 구성된 검증 체인을 사용한다.

### Invariants
1. 모든 `Finalized=true` 이벤트는 변경/삭제될 수 없다.
2. 이벤트 시퀀스는 Tombstone 포함 단조 증가하며, “중간 공백”이 존재할 수 없다.
3. `commit_hash`–`event_root`–`event_body_hash`의 3자 검증이 항상 가능해야 한다.

---

## 2687. 업그레이드 결정론(Deterministic Upgrade) 전제 및 스키마/규칙 버저닝

### Purpose
프로토콜 업그레이드가 발생해도 과거 상태의 재현성과 감사 가능성을 훼손하지 않도록 결정론적 업그레이드 모델을 정의한다.

### Architecture or Rule
1. 모든 이벤트와 스냅샷은 `protocol_version`을 포함한다.
2. 실행 규칙은 `protocol_version`에 의해 선택되며, 과거 버전에 대한 실행기(Interpreter)는 유지되어야 한다(후방 호환).
3. 업그레이드 유형:
   - **Non-breaking**: 스키마 필드 추가, 검증 강화(기존 유효 트랜잭션을 무효화하지 않는 범위)
   - **Breaking(제한적 허용)**: 기존 의미 변경/삭제, 과거 이벤트 해석 불가 변경
4. Breaking 변경 허용 조건(최소 요건):
   1) 합의로 고정된 `activation_epoch`를 가져야 한다.
   2) `activation_epoch` 이전 구간을 위한 **레거시 규칙 집합(legacy rule set)** 및 디코더를 제공해야 한다.
   3) 리플레이 키트(2690)의 “규칙/디코더 식별자”가 갱신되어야 하며, 디코더/규칙 문서의 해시를 제공해야 한다.
   4) 거버넌스 승인 절차는 본 장에서 구체 절 번호를 제시하지 않으며 [REFERENCE_REQUIRED]로 남긴다.
5. `schema_version`은 `protocol_version`과 독립적으로 증가 가능하나, **동일 `(protocol_version, schema_version)` 조합에 대한 해석은 단일**이어야 한다. 호환성 매트릭스 문서는 [REFERENCE_REQUIRED]로 둔다.

### State/Flow
- 업그레이드 활성화는 합의 커밋 시점의 `activation_epoch`로 고정한다.
- `activation_epoch` 이전 이벤트는 구버전 규칙으로만 해석한다.

### Validation
- 동일 `tx_id`에 대해 서로 다른 해석이 발생하지 않도록 버전 선택 규칙은 단일해야 한다.
- 업그레이드 규칙 불일치가 탐지되면 해당 노드는 동기화를 중단하고 “버전 불일치”로 격리한다(원장 분기 방지).

### Failure handling
- 버전/디코더 불일치 시:
  - 해당 노드는 Canonical State를 수용하지 않고 격리 상태로 전환한다.
  - 운영자는 레거시 규칙/디코더 제공 여부를 점검해야 한다.

### Audit
- 감사 도구는 `protocol_version`별 디코더를 포함해야 하며, 디코더 변경 이력도 해시로 보존할 수 있다.

### Invariants
- Backward-compatible constitutional invariants 유지.
- Canonical ledger state determinism 유지.

---

## 2688. GLPF 감사 이벤트 객체 모델(Object Model) — 구현 준비 스펙

### Purpose
GLPF에서 사용되는 감사 이벤트/스냅샷/커밋 바인딩의 구현 가능한 객체 모델을 제시한다.

### Architecture or Rule
아래 객체 모델은 향후 레지스트리에 등록되기 전까지 **Non-canonical(등록 전 사용 금지)** 초안 스키마로 취급한다([REFERENCE_REQUIRED]).

또한 GLPF 감사 이벤트는 **원금 소유권 NFT(Principal Ownership NFT)의 상태를 변경하지 않는다**. 원금 소유권 변경을 수반하는 이벤트는 GLPF 스트림이 아니라, 별도 원금/준비금 레이어에서만 발생해야 한다(권리 분리 원칙 준수).

### State/Flow (Object Definitions)
```move
/// [DRAFT] GLPF 공통 컴플라이언스 태그
public struct ComplianceTag has drop, store {
    reserve_id: ID,
    custodian_id: ID,                 // 행위 시점의 custodian
    custodian_effective_epoch: u64,    // custodian 해석 기준 epoch(권고 필수)
    reason_code: u32,
    jurisdiction_code: option<u16>,
    kyc_tier: option<u8>,
    sanctions_screening_ref: option<vector<u8>>,
    policy_ref: option<vector<u8>>,
}

/// [DRAFT] 이벤트 공통 헤더(총순서 포함)
public struct AuditEventHeader has drop, store {
    schema_id: u32,
    schema_version: u16,
    event_type: u16,
    protocol_version: u32,

    // 총순서 튜플
    commit_epoch: u64,
    commit_id: u64,
    tx_id: vector<u8>,        // 32 bytes 권고(해시)
    tx_index: u32,
    event_index: u32,

    // 식별자
    event_id: vector<u8>,     // 32 bytes: H(commit_hash || tx_id || event_index || schema_id || event_type)

    actor: address,
}

/// [DRAFT] 상태 스냅샷(요약)
public struct GLPFStateSnapshot has drop, store {
    snapshot_id: vector<u8>,      // 32 bytes: H(commit_hash || snapshot_scope || state_hash)
    snapshot_epoch: u64,          // commit_epoch와 동일 규칙
    protocol_version: u32,
    schema_version_set: vector<u16>,
    state_hash: vector<u8>,       // 32 bytes 권고
}

/// [DRAFT] 액션 이벤트(가변 payload는 타입별로 별도 정의)
public struct GLPFAuditActionEvent has drop, store {
    header: AuditEventHeader,
    compliance: ComplianceTag,

    // 감사 추적 식별자(필수)
    pool_id: ID,
    ft_type: vector<u8>,          // 경제적 활용 FT 타입/식별자(표준 인코딩)
    economic_token_id: option<ID>,// 필요 시 FT 객체/코인 객체 식별자

    // Gate A/B 재현 참조(필수)
    validation_result_hash: vector<u8>,
    authorization_proof_ref: vector<u8>,

    pre_state_hash: vector<u8>,
    post_state_hash: vector<u8>,
    payload_hash: vector<u8>,     // payload canonical encoding hash
}

/// [DRAFT] 리젝/실패 이벤트(최소 정보)
public struct GLPFAuditRejectOrFailEvent has drop, store {
    header: AuditEventHeader,
    compliance: ComplianceTag,
    pool_id: option<ID>,
    ft_type: option<vector<u8>>,

    failed_gate: u8,              // 1=A,2=B,3=C,4=D
    reject_code: u32,
    cause_hash: option<vector<u8>>,

    pre_state_hash: vector<u8>,
    post_state_hash: vector<u8>,  // 기본: pre == post
}

/// [DRAFT] 커밋 바인딩
public struct ConsensusCommitBinding has drop, store {
    header: AuditEventHeader,     // event_type = COMMIT_BINDING
    commit_type: u8,
    commit_id: u64,
    commit_hash: vector<u8>,      // 32 bytes 권고
    commit_epoch: u64,
    event_root: vector<u8>,       // 32 bytes 권고
}
```

### Validation
- `event_id` 생성 규칙(표준):
  - `event_id = H(commit_hash || tx_id || event_index || schema_id || event_type)`
  - 해시 출력 길이는 32 bytes를 권고하며, 해시 함수는 프로토콜이 지정한 단일 알고리즘을 사용해야 한다.
- `tx_id`, `commit_hash`, `state_hash`, `event_root`는 고정 길이(권고 32 bytes) 및 단일 바이트 인코딩을 사용하며, hex/base64 등은 오프체인 표현에 한정한다.
- `payload_hash`는 타입별 payload의 정규화 인코딩 해시여야 한다.
- `pre_state_hash`/`post_state_hash`는 스냅샷 계산 규칙과 일치해야 한다.
- `ConsensusCommitBinding.event_root`는 해당 범위 이벤트에 대한 Merkle root로 검증 가능해야 한다.

### Failure handling
- 객체 생성/저장 단계에서 해시 불일치가 발생하면 즉시 중단하고, `FAILED` 이벤트로 기록되어야 하며 커밋 확정에 반영될 수 없다.

### Audit
- 감사자는 `GLPFAuditActionEvent`와 `ConsensusCommitBinding`을 결합하여 “Finalized 감사 이벤트”를 구성한다.

### Invariants
- 이벤트/스냅샷/커밋 바인딩의 해시 체인은 끊길 수 없으며, 삭제 대신 Tombstone만 허용한다.

---

## 2689. 통제 지점(Control Points): 검증·권한·감사·합의의 결합 강제

### Purpose
GLPF가 “편의”를 이유로 준비금/소유권/합의/감사 불변식을 우회하지 못하도록 시스템 통제 지점을 명시한다.

### Architecture or Rule
1. 통제 지점은 다음 4개 게이트로 구성된다.
   - Gate A: Business Rule Validation
   - Gate B: Execution Authorization
   - Gate C: Audit Recording(총순서/스키마/태그)
   - Gate D: Consensus Commit Binding
2. Gate C 또는 Gate D를 통과하지 못한 상태 전이는 Canonical State로 반영될 수 없다.
3. Gate D 실패(CommitFailure) 시에도 Gate C에서 기록된 이벤트는 폐기되지 않으며, `UNFINALIZED/FAILED`로 유지되고 비확정 구간으로 봉인된다(2683).

### State/Flow
- 각 트랜잭션 실행 파이프라인은 Gate A→B→C→D의 순서를 변경할 수 없다.

### Validation
- Gate별 필수 산출물:
  - A: 검증 결과(`validation_result_hash`, `reject_code`)
  - B: 권한 증명 참조(`authorization_proof_ref`)
  - C: 감사 이벤트(고정 스키마 + 컴플라이언스 + 총순서)
  - D: 커밋 바인딩(합의 증명)

### Failure handling
- Gate별 실패는 상호 전이되지 않으며, 실패 원인은 단일 코드로 표준화한다(감사 및 통계 목적).
- 실패는 반드시 `REJECTED/FAILED` 이벤트로 기록된다.

### Audit
- Gate A/B 통과 사실은 `validation_result_hash`, `authorization_proof_ref`, `policy_ref`(컴플라이언스 확장 또는 별도 필드)로 재현 가능해야 한다.

### Invariants
- No Unauthorized Execution
- No Invalid Settlement
- No Audit Inconsistency

---

## 2690. 검증 가능성(Verifiability) 패키지: 리플레이 키트 및 감사 인터페이스 요구사항

### Purpose
외부 기관이 GLPF의 결정론·감사·컴플라이언스를 독립적으로 검증할 수 있도록, 최소 제공 인터페이스를 정의한다.

### Architecture or Rule
1. 노드는 다음 조회를 제공해야 한다(논리 인터페이스; 구현체는 체인/인덱서에 따라 상이 가능).
   - `get_snapshot(snapshot_id | epoch)`
   - `get_events(range, finalized_only=true, filters={reserve_id, custodian_id, event_type, reason_code, pool_id, ft_type})`
   - `get_commit_binding(commit_id | epoch)`
2. 리플레이 키트(Replay Kit)는 다음을 포함한다.
   - 기준 스냅샷
   - Finalized 이벤트 스트림(2682 총순서 튜플 포함)
   - 해당 구간의 `protocol_version`/`schema_version_set`
   - 정규화 인코딩 규칙 문서 해시(`policy_ref`) 또는 버전 식별자
   - 디코더/레거시 규칙 식별자 및 해시(2687 요건)

### State/Flow
- 감사자는 리플레이 키트를 취득 후 독립 실행으로 `state_hash` 일치를 검증한다.
- 불일치 시 2684의 “Determinism Incident” 절차로 이관한다.

### Validation
- 인터페이스 응답은 커밋 바인딩으로 무결성이 검증 가능해야 한다(이벤트 루트 포함).

### Failure handling
- 인덱서 장애 등으로 이벤트 조회가 불가한 경우에도, 온체인 커밋/이벤트 원본으로부터 재구축 가능해야 한다(장기 보존 요구).

### Audit
- 리플레이 키트 생성/제공 행위 자체도 감사 대상이 될 수 있으므로, 제공 로그의 해시를 보존할 수 있다(선택).

### Invariants
- Long-Term Audit Preservation 및 Deterministic Upgrade 전제는 GLPF의 모든 상위 모듈(수익 분배, Treasury, Insurance, DAO)에서 동일하게 상속되어야 한다.

<-bash: cd: /home/boshin57/tobmate-agent-factory: No such file or SOURCE: workspace/drafts/3O_2691_2700_approved.md -->
```markdown
## 2691. 목적(Purpose)

### 2691.1 GLPF 완료 불변식(Completion Invariants)의 정의 목적
본 절은 Chapter 3O — Gold Liquidity Pool Framework(GLPF)가 **실행 가능한 경제 계층(Executable Economic Layer)** 으로서 “완료(Completion)” 상태에 도달하기 위해 반드시 충족해야 하는 **GLPF 고유** 불변식(Invariants)과 종결성(Finality) 규칙을 정의한다.

### 2691.2 다음 장 전환(Transition to Next Chapter)의 정의 목적
본 절은 GLPF가 Chapter 3N에서 확립된 헌법적 불변(Constitutional Invariants)을 **추가·변경 없이 상속(Constitutional Inheritance)** 하는 범위에서 완결되었음을 선언하고, 후속 장(Chapter 3P 또는 후속 프레임워크)로의 전환 조건과 전환 선언 포맷을 정의한다. 단, 다음 장의 식별은 [REFERENCE_REQUIRED]에 의해 확정되어야 한다.

---

## 2692. 아키텍처/규칙(Architecture or Rule)

### 2692.1 단일 실행 스택 결합 완료 조건(Single Execution Stack Completion)
GLPF는 아래 구성요소가 **단일 실행 스택(Single Execution Stack)** 으로 결합되어, 모든 유동성 관련 상태 전이가 동일한 검증·권한·감사·합의 경로를 통과할 때 “완료”로 간주한다.

- 객체 모델(Object Model): Liquidity Pool Object, Position/Share Object, Fee/Revenue Accumulator, Distribution Output Object(정산 산출물)
- 상태기계(State Machine): pool/position/fee/distribution의 상태 전이 규칙
- 검증(Validation): Business Rule Validation Framework(BRVF) 호출 경로의 강제
- 권한(Authorization): Execution Authorization Framework(EAF) 카테고리 적용 강제
- 감사(Audit): 커밋 결합형 감사(Commit-attached Audit) 또는 2단계 감사(2693.2, 2696.1)의 강제
- 합의(Consensus): Validator 합의에 의해 최종 상태가 결정론적으로 확정

> 주의: GLPF는 Treasury/Insurance/DAO 자산을 **직접 이동/혼합하지 않는다.** GLPF는 오직 `Distribution Output Object`를 생성하며, 외부 모듈 호출은 “외부 호출 기술자(External Module Call Descriptor)” 수준의 메타데이터로만 표현한다. 해당 모듈(TRF/IRF/DGF)의 객체 모델 및 상태 전이는 [REFERENCE_REQUIRED]이다.

### 2692.2 헌법 불변식 상속 준수(Constitutional Inheritance Compliance)
GLPF는 Chapter 3N에서 확립된 헌법적 불변식(예: Reserve Before Issuance, Principal Ownership Protection, Rights Separation, Deterministic Canonical State, Validation/Authorization/Consensus/Audit 선행 원칙 등)을 **재정의하지 않으며**, 다음의 형태로만 적용한다.

- **적용 범위(Scope)**: GLPF의 모든 엔트리포인트(Entry Point), 풀/포지션/누적기/정산 산출물 생성 및 갱신 경로
- **준수 방식(Enforcement)**: BRVF 사전 검증 + EAF 권한 검증 + 합의 기반 종결 + 감사 추적성의 결합
- **검증 산출물(Evidence)**: 각 실행은 정책 버전, 권한 카테고리, 대상 객체의 변경 전/후 다이제스트(digest), 종결 참조(finality reference)를 포함하는 감사 레코드로 입증되어야 한다.

### 2692.3 유동성 작업 우회 금지 불변식(Bypass Prohibition Invariant)
어떠한 유동성 관련 작업도 다음 불변 경로를 우회할 수 없다.

- Reserve 불변 경로(Reserve Invariant Path): 준비금 선행 및 준비금 상태 일관성(상속 불변식 준수의 일부)
- Ownership 불변 경로(Ownership Invariant Path): 원금 소유권 NFT(Principal Ownership NFT) 무단 변경/침해 금지(상속 불변식 준수의 일부)
- Consensus 불변 경로(Consensus Invariant Path): 최종 상태는 합의 기반으로 확정
- Audit 불변 경로(Audit Invariant Path): 모든 경제적 상태변경은 감사 레코드를 남김(2696.1의 감사-종결 결합 규칙 준수)

---

## 2693. 상태/흐름(State/Flow)

### 2693.1 GLPF 완료 상태(Completion State) 정의
GLPF의 “완료”는 단일 플래그가 아니라, 아래 완료 조건들의 **동시 성립(Conjunctive Completion)** 으로 정의된다.

1. (객체) 유동성 관련 핵심 객체들이 불변식에 의해 참조 무결성(Referential Integrity)을 갖는다.
2. (상태기계) 모든 상태 전이가 결정론적이며, 동일 입력은 동일 결과를 산출한다.
3. (검증) 모든 진입점(Entry Point)이 BRVF 검증을 강제한다.
4. (권한) 모든 변경(Write)이 EAF 권한을 강제한다.
5. (감사) 모든 실행은 2단계 감사 또는 커밋 결합형 감사로 기록되며, 종결 상태와 모순되지 않는다.
6. (합의) 최종 상태는 Validator 합의에 의해 확정되고, 재실행 시 동일하게 재현된다.

### 2693.2 실행 흐름 표준 형식(Standard Execution Flow)
GLPF의 모든 상태 전이는 아래 순서를 반드시 따른다(2단계 감사 모델).

1. 입력 정규화(Input Normalization)
2. BRVF 사전 검증(Pre-Validation)
3. EAF 권한 검증(Authorization Check)
4. 상태 전이 계산(Deterministic Transition Computation)
5. 사전-감사 기록(Pre-Audit Write; `audit_status=PENDING`)
6. 합의 기반 확정(Consensus Finality)
7. 원장 반영(Ledger Commit; 확정 참조 포함)
8. 확정-감사 승격(Final Audit Promote; `audit_status=FINAL`, `validator_finality_ref` 결합)
9. 사후 검증(Post-Invariant Check)

- `PENDING` 감사는 종결에 대한 주장(finality claim)을 포함할 수 없으며, 2696.2.4의 결정론적 전이 규칙에 의해 `FINAL` 또는 `REVERTED`로만 귀결되어야 한다.

---

## 2694. 검증(Validation)

### 2694.1 완료 검증(Completion Validation) 체크리스트
GLPF 완료 검증은 아래 항목을 모두 통과해야 한다.

- (V-1) 모든 유동성 엔트리포인트가 BRVF를 호출하며, BRVF 미통과 시 상태 변경이 불가능
- (V-2) 모든 객체 변경이 EAF 권한 카테고리 중 최소 1개 이상을 요구하며, 권한 누락 시 거절
- (V-3) Reserve/Ownership/Consensus/Audit 우회 경로가 존재하지 않음(정적/동적 점검 대상)
- (V-4) `Distribution Output Object`가 Value Source–Reward Correspondence(2695)를 만족하지 못하면 생성 불가
- (V-5) 실패 시 롤백/정지 규칙이 결정론적으로 적용됨(2696 참조)

### 2694.2 정책/버전 정합성(Policy/Version Consistency)
GLPF는 정책(Policy) 및 버전(Version) 불일치 시 실행을 금지한다.

- 정책 미존재: 거절
- 정책 버전 불일치: 거절
- 승인 만료: 거절

본 절은 공통 에러 코드 체계를 전제하지 않으며, 실패 응답/감사에는 최소 다음 필드를 포함해야 한다.

- `error_domain` (예: `BRVF`, `EAF`, `GLPF`)
- `error_code`
- `policy_id`
- `policy_version`
- `invariant_id` (해당 시)
- `caller` 및 `tmoid/tmid_ref` (가능한 경우)

공통 코드 체계의 정식 정의는 [REFERENCE_REQUIRED]이다.

---

## 2695. 수익원-보상 대응 불변식(Value Source–Reward Correspondence Invariant)

### 2695.1 목적
모든 경제적 보상(Reward)은 반드시 **정의된 가치 원천(Defined Value Source)** 에 대응되어야 하며, 감사 가능해야 한다.

### 2695.2 규칙
- 보상은 다음 조건을 만족하지 못하면 생성/분배될 수 없다.
  1. 수익원 유형(type)이 명시됨
  2. 수익원 산출식(formula)이 결정론적임
  3. 수익원 입력 데이터(input)가 온체인 또는 감사 가능한 오프체인 증빙으로 연결됨
  4. 분배 기준(distribution rule)이 정책으로 고정됨
  5. 각 수익 분배 레코드가 원천 수익 레코드를 역추적 가능함(linkable)

- GLPF 범위에서 본 불변식은 다음에 직접 적용된다.
  - Fee/Revenue Accumulator의 증가(누적) 이벤트
  - `Distribution Output Object`의 산출(정산 출력)

- Treasury/Insurance/DAO로의 실제 자산 반영(상태 변경) 규칙은 각 상위 모듈(TRF/IRF/DGF)의 정의에 의해 **추가 제한**되며, 본 절에서는 이를 규정하지 않는다([REFERENCE_REQUIRED]).

### 2695.3 감사 레코드 요구(Audit Record Requirements)
수익원 및 보상 분배는 최소 아래 필드를 포함하는 감사 레코드를 남겨야 한다.

- `value_source_id`
- `value_source_type`
- `value_source_inputs_digest`
- `gross_amount`
- `net_amount`
- `distribution_policy_id`
- `distribution_outputs_digest`
- `beneficiary_set_digest`
- `epoch` 또는 `settlement_id`
- `validator_finality_ref` (FINAL에 한함)
- `audit_status` (`PENDING`/`FINAL`/`REVERTED`)

---

## 2696. 종결성(Finality) 및 실패 처리(Failure handling)

### 2696.1 상태 전이 종결성(Finality) 원칙
- 최종 상태(Final State)는 Validator 합의에 의해 확정되며, 확정 후에는 동일 트랜잭션 의미론이 재실행되어도 결과가 변하지 않는다.
- 종결성은 “감사 포함 종결성(Audit-inclusive Finality)”으로 정의되며, `FINAL` 감사 레코드는 반드시 해당 확정 참조(`validator_finality_ref`)에 결합되어야 한다.
- `PENDING` 감사는 canonical 최종 상태를 주장하지 않으며, 2696.2.4의 규칙에 의해 반드시 `FINAL` 또는 `REVERTED`로 **결정론적으로** 전이되어야 한다.

### 2696.2 실패 유형별 처리 규칙
1. **검증 실패(Validation Failure)**  
   - 상태 변경: 미발생  
   - 감사: 실패 이벤트 기록(거절 사유 포함, `audit_status=REVERTED` 또는 “미생성” 중 정책으로 결정)  
   - 결과: 즉시 거절(Reject)

2. **권한 실패(Authorization Failure)**  
   - 상태 변경: 미발생  
   - 감사: 실패 이벤트 기록(권한 카테고리 및 결여 항목 포함, `audit_status=REVERTED` 또는 “미생성” 중 정책으로 결정)  
   - 결과: 즉시 거절(Reject)

3. **불변식 위반(Invariant Violation)**  
   - 상태 변경: 롤백(Rollback)  
   - 감사: 위반 이벤트 기록(위반 불변식 ID 포함, `audit_status=REVERTED`)  
   - 결과: 정지(Stop) 또는 비상 정책(Emergency Policy)에 따른 동결(Freeze) 전이(단, 동결 전이는 Emergency Authorization을 요구)

4. **합의 실패/확정 실패(Consensus/Finality Failure)**  
   - 상태 변경: FINAL로 확정되지 않은 변경은 canonical state에 반영될 수 없음  
   - 감사: `PENDING` 감사가 존재하는 경우, 결정론적 조건에 의해 `REVERTED`로 전이  
   - 결과: 재시도는 정책에 의해 제한되며, 재시도 시 재플레이 방지(Replay Protection)를 강제

### 2696.3 롤백/정지의 결정론성(Deterministic Rollback/Stop)
- 롤백 및 정지 조건은 입력, 정책 버전, 현재 상태의 조합으로 **결정론적으로** 계산되어야 하며, 임의 재량 경로를 금지한다.
- 정지(Stop)/동결(Freeze) 전이는 Emergency Authorization을 요구한다(카테고리 매핑은 EAF 정의에 종속).

### 2696.4 PENDING 감사의 결정론적 전이(PENDING Audit Deterministic Resolution)
`PENDING` 감사는 canonical ledger state 내에 기록될 수 있으며, 그 경우 다음 전이 규칙은 결정론적이어야 한다.

- 전이 입력(Deterministic Inputs)
  - `tx_digest` (또는 동등한 idempotency key)
  - `epoch` 또는 `finality_window_id`
  - `policy_version`
- 전이 규칙(State Transitions)
  - `PENDING → FINAL`: `validator_finality_ref`가 관측/결합되면 즉시 승격
  - `PENDING → REVERTED`: `finality_window_id` 만료 시 승격 실패로 확정(타임아웃 기준은 epoch 또는 프로토콜 정의 창(window)이며 [REFERENCE_REQUIRED])
- 재시도/중복 실행(Idempotency)
  - 동일 `tx_digest`에 대한 재시도는 기존 `PENDING/FINAL/REVERTED` 상태를 조회하여 동일 결과를 반환해야 하며, 중복 분배/중복 누적을 금지한다.

---

## 2697. 감사(Audit)

### 2697.1 GLPF 완료 감사 요건(Completion Audit Requirements)
GLPF 완료는 아래 감사 가능성 조건을 포함한다.

- 모든 유동성 작업은 **요청(Request) → 검증(Validation) → 권한(Authorization) → 실행(Execution) → 정산 산출(Distribution Output) → 확정(Finality)** 전 구간이 단일 Trace로 연결된다.
- 각 Trace는 다음을 포함해야 한다.
  - 호출자(Caller) 및 TMID 연계(가능한 경우)
  - 대상 객체(Object IDs) 및 변경 전/후 Digest
  - 정책(Policy) 및 버전(Version)
  - 권한 카테고리(Authorization Category)
  - 합의 참조(Validator Finality Reference; `FINAL`에 한함)
  - 감사 상태(`audit_status`)

### 2697.2 감사 보존 및 조회 불변(Audit Retention/Query Invariant)
- 감사 레코드는 경제 객체의 수명(Lifetime)을 초과하여 보존되어야 한다(Audit Beyond Lifetime).
- 조회 가능성은 데이터 삭제/축약 정책에 의해 훼손되어서는 안 된다.

---

## 2698. 불변식(Invariants)

### 2698.1 헌법 불변식 상속(Constitutional Invariants — Inherited)
GLPF는 Chapter 3N에서 확립된 헌법 불변식을 **상속**하며, 본 절은 이를 재정의하지 않는다. 상속 불변식의 정식 목록/식별자(invariant_id)는 [REFERENCE_REQUIRED]이며, GLPF는 2692.2 및 2694의 방식으로 준수를 강제한다.

### 2698.2 GLPF 고유 완료 불변식(GLPF-Specific Completion Invariants)
아래 불변식은 GLPF 완료의 필요조건이며, 유동성 풀/포지션/수수료 회계/정산 산출물의 실행 계층에서 직접 검증되어야 한다.

1. **Pool Accounting Segregation**: 풀 단위 회계(assets/liabilities/fees)는 풀 경계를 넘어 혼합될 수 없다.
2. **Position Conservation**: LP 포지션(share/position)의 생성·증감·소각은 정책과 입력에 의해 결정론적으로 계산되며, 무단 생성/무단 소각이 불가능해야 한다.
3. **Monotonic Fee Accumulator**: Fee/Revenue Accumulator는 정책이 허용하는 경우를 제외하고 단조 증가(monotonic)해야 하며, 음수 누적/역전이 불가능해야 한다.
4. **Deterministic Distribution Output**: 동일 입력(상태, 정책 버전, 누적기 스냅샷, epoch)에서 `Distribution Output Object`는 동일 결과를 산출해야 한다.
5. **Distribution Idempotency**: 동일 정산 식별자(settlement_id 또는 동등 키)에 대한 분배 산출은 멱등(idempotent)해야 하며, 중복 산출/중복 누적을 금지한다.
6. **Module Boundary Non-Transfer**: GLPF는 외부 모듈(Treasury/Insurance/DAO)로의 직접 자산 이동을 수행하지 않으며, 오직 정산 산출물과 호출 기술자만 생성할 수 있다.
7. **Audit-Finality Consistency**: `FINAL` 감사 레코드는 반드시 합의 확정 참조에 결합되며, `PENDING`은 결정론적으로 `FINAL/REVERTED`로만 전이되어야 한다(2696.4).

### 2698.3 분리 원칙 준수(Separation Compliance)
- Treasury, Insurance Reserve, Protocol Revenue, User Asset은 반드시 분리 관리되어야 하며, GLPF는 이 분리를 훼손하는 자산 이동을 생성할 수 없다.
- 분리 회계의 정식 객체/계정 구조는 상위 모듈(TRF/IRF) 정의에 종속되며 [REFERENCE_REQUIRED]이다. 단, GLPF는 2698.2.6을 통해 경계 위반을 구조적으로 금지해야 한다.

---

## 2699. 다음 장 전환(Transition to Next Chapter)

### 2699.1 전환 선언(Transition Declaration)
GLPF의 전환은 새로운 헌법을 도입하는 것이 아니라, Chapter 3N에서 확립된 헌법적 불변을 **그대로 상속(Constitutional Inheritance)** 한 상태에서 경제 계층을 확장하는 선언으로 정의된다.

### 2699.2 전환 조건(Transition Preconditions)
다음 조건이 모두 만족되면, GLPF는 후속 장으로 전환 가능하다.

- 2692~2698의 완료 조건이 충족됨(특히 2698.2 GLPF 고유 완료 불변식 충족)
- 실패 처리/종결성 규칙(2696)이 모듈 전 구간에 적용됨
- 수익원-보상 대응 불변식(2695)이 정산 산출물까지 관통 적용됨
- 헌법 불변식 상속 준수(2692.2)가 엔트리포인트 전 구간에서 입증됨

### 2699.3 후속 장 식별자(Next Chapter Identifier)
후속 장은 본 문서의 정식 인덱스에 의해 확정되어야 한다.

- Chapter 3P: [REFERENCE_REQUIRED]
- 후속 프레임워크 명칭: [REFERENCE_REQUIRED]
- 근거 문서: [REFERENCE_REQUIRED]

---

## 2700. 장 완료 선언(Chapter Completion Statement)

### 2700.1 GLPF 완료 선언
본 절에서 정의한 완료 조건 및 GLPF 고유 불변식은 GLPF가 “객체/상태기계/검증/권한/감사/합의”를 단일 실행 스택으로 결합하여, 준비금 기반 유동성 경제의 정산 산출물을 결정론적으로 생성할 수 있음을 보장하기 위한 최소 필요조건이다.

### 2700.2 헌법 영구 적용 선언(Constitutional Permanence)
GLPF는 Chapter 3N에서 확립된 헌법(Constitution) 및 상위 불변식을 변경하지 않으며, 이후 모든 상위 경제 모듈은 상속 불변식 준수 및 GLPF 경계 불변식(특히 자산 분리 및 직접 자산 이동 금지)을 위반하는 방식으로 확장될 수 없다.

### 2700.3 후속 장 전환 선언(Transition Charter)
이로써 Chapter 3O — Gold Liquidity Pool Framework(GLPF)는 완료 불변식 및 전환 조건을 확정하며, 후속 장(Chapter 3P 또는 후속 프레임워크)로의 전환은 2699.3의 [REFERENCE_REQUIRED]가 충족되는 즉시 선언될 수 있다.
