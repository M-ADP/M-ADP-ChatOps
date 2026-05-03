# ChatOps SSE 메트릭 — 인프라/Grafana 핸드오프

## 1. 노출 정보

| 항목 | 값 |
|---|---|
| 엔드포인트 | `GET /metrics` |
| 포맷 | Prometheus exposition (text) |
| 컨테이너 포트 | 8000 |
| Path | `/metrics` (인증 불필요, 내부망 전용) |
| 서비스 (dev) | `chatops-dev` (namespace: `chatops-dev`) |

## 2. 노출되는 메트릭

| 메트릭 | 타입 | 라벨 | 설명 |
|---|---|---|---|
| `sse_connections_active` | Gauge | — | 현재 활성 SSE follow 연결 수 |
| `sse_connections_total` | Counter | `outcome` | 누적 연결 수. `outcome ∈ {opened, closed_normal, client_disconnect, closed_error}` |
| `sse_events_sent_total` | Counter | — | 클라이언트에 전송된 SSE 이벤트 누적 수 |
| `sse_db_polls_total` | Counter | — | follow 모드의 DB 폴링 누적 횟수 (100ms 주기) |
| `sse_connection_duration_seconds` | Histogram | — | 연결 유지 시간. buckets: 1, 5, 15, 30, 60, 120, 300, 600, 1800, 3600 |

## 3. Prometheus scrape 설정

### ServiceMonitor (Prometheus Operator 사용 시)
```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: chatops-sse
  namespace: chatops-dev
spec:
  selector:
    matchLabels:
      app: chatops-dev
  endpoints:
    - port: http  # 8000번 포트의 named port
      path: /metrics
      interval: 15s
```

### Pod annotation 방식 (kube-prometheus 기본 scrape)
```yaml
metadata:
  annotations:
    prometheus.io/scrape: "true"
    prometheus.io/port: "8000"
    prometheus.io/path: "/metrics"
```

## 4. Grafana 대시보드 패널 (PromQL)

### 4-1. 활성 연결 수
```promql
sse_connections_active
```
Panel: Time series, unit: short

### 4-2. 신규 연결 / 종료 비율 (분당)
```promql
sum by (outcome) (rate(sse_connections_total[1m])) * 60
```
Panel: Time series, stack by `outcome`

### 4-3. 비정상 종료 비율
```promql
sum(rate(sse_connections_total{outcome=~"closed_error|client_disconnect"}[5m]))
  /
sum(rate(sse_connections_total{outcome="opened"}[5m]))
```
Panel: Stat, unit: percent (0.0–1.0)

### 4-4. DB 폴링 부하 (qps)
```promql
rate(sse_db_polls_total[1m])
```
Panel: Time series. **이상 신호:** `sse_connections_active * 10 ≈ rate(sse_db_polls_total)` 가 되어야 정상 (100ms 주기). 크게 벗어나면 폴링 루프 이상.

### 4-5. 연결당 평균 폴링 부하
```promql
rate(sse_db_polls_total[1m]) / sse_connections_active
```
Panel: Stat. **기댓값:** ~10/s/connection.

### 4-6. 이벤트 전송 처리량
```promql
rate(sse_events_sent_total[1m])
```

### 4-7. 연결 지속 시간 분포 (p50/p95/p99)
```promql
histogram_quantile(0.50, rate(sse_connection_duration_seconds_bucket[5m]))
histogram_quantile(0.95, rate(sse_connection_duration_seconds_bucket[5m]))
histogram_quantile(0.99, rate(sse_connection_duration_seconds_bucket[5m]))
```

## 5. 추천 Alert 룰

```yaml
groups:
  - name: chatops-sse
    rules:
      - alert: SSEHighActiveConnections
        expr: sse_connections_active > 30
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "SSE 활성 연결이 uvicorn 워커 풀 한계(~40)에 근접"
          description: "현재 {{ $value }}개. sync 핸들러 구조라 ~40을 넘기면 신규 요청이 막힘."

      - alert: SSEErrorRateHigh
        expr: |
          sum(rate(sse_connections_total{outcome="closed_error"}[5m]))
            /
          sum(rate(sse_connections_total{outcome="opened"}[5m]))
            > 0.05
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "SSE 비정상 종료율 5% 초과"

      - alert: SSEDBPollingAnomaly
        expr: |
          rate(sse_db_polls_total[1m])
            /
          (sse_connections_active * 10)
            > 1.5 or
          (
            sse_connections_active > 0
            and rate(sse_db_polls_total[1m]) == 0
          )
        for: 3m
        labels:
          severity: critical
        annotations:
          summary: "SSE 폴링 루프 이상 감지"
```

## 6. 컨텍스트 (왜 이 메트릭이 중요한가)

이 서비스의 SSE 구현은 다음 운영 한계가 있어 모니터링이 필요합니다:

1. **sync 핸들러 + worker thread 점유** — 1 연결 = uvicorn worker thread 1개. 기본 thread pool ~40 → 동시 SSE 상한이 ~40. `sse_connections_active`가 30 넘기 시작하면 위험 신호.

2. **DB 폴링 (event-driven push 아님)** — 모든 follow 연결이 100ms마다 독립적으로 DB를 조회. 연결 N개 = **초당 10N qps**가 DB로. `sse_db_polls_total` rate를 보면 부하 추정 가능.

3. **클라이언트 disconnect 가시성 부족** — `client_disconnect` 라벨로 추적. 장기적으로 비율이 높아지면 네트워크/프록시 timeout 의심.

4. **메트릭 자체가 후속 개선의 검증 수단** — 향후 async 전환 / Postgres LISTEN-NOTIFY 도입 등 개선 시, 위 메트릭으로 효과 측정.

## 7. 검증 방법 (배포 후)

```bash
kubectl exec -it <chatops-pod> -n chatops-dev -c chatops-dev -- \
  curl -s http://localhost:8000/metrics | grep -E "^sse_"
```

기대 출력 예:
```
sse_connections_active 0.0
sse_connections_total{outcome="opened"} 0.0
sse_db_polls_total 0.0
sse_events_sent_total 0.0
sse_connection_duration_seconds_bucket{le="1.0"} 0.0
...
```
