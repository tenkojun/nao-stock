<div align="center">

<img src="assets/nao.png" width="104" alt="NAO STOCK">

# NAO STOCK

### 예측하지 않습니다. 계산하고 기록합니다.

한국주식 장기투자 분석기 · 데스크톱 프로그램

<br>

![version](https://img.shields.io/badge/version-1.3.0-1b1917?style=for-the-badge&labelColor=e8e3d6)
![python](https://img.shields.io/badge/python-3.9+-7a2018?style=for-the-badge&labelColor=e8e3d6)
![platform](https://img.shields.io/badge/windows-10%20%C2%B7%2011-3a4a63?style=for-the-badge&labelColor=e8e3d6)
![license](https://img.shields.io/badge/license-MIT-5c6b4a?style=for-the-badge&labelColor=e8e3d6)

</div>

<br>

---

## 왜 만들었나

매달 여윳돈이 생기면 어차피 삽니다. 몇 달에서 1년쯤 들고 있고,
떨어지면 더 사서 평단을 낮추기도 합니다. 대부분의 장투는 이렇게 굴러갑니다.

이런 매매에 정작 필요한 건 "오를까요 내릴까요"에 대한 대답이 아닙니다.
**계좌가 한쪽으로 쏠려 있지는 않은지, 이번 달 여윳돈을 어떻게 나눌지,
세금과 수수료를 빼면 실제로 얼마가 남는지** — 계산하면 확실하게 답이 나오는 것들입니다.

예측은 틀릴 수 있지만 계산은 틀리지 않습니다. 그래서 계산만 합니다.

<br>

## 하는 일 / 하지 않는 일

<table>
<tr>
<td width="50%" valign="top">

### ✅ 합니다 — 계산과 기록

- 이번 달 여윳돈 배분 계산
- 계좌 쏠림·집중도 진단
- 세금·수수료·호가 스프레드 왕복비용
- 변동성·분산 계산
- 매매 이유와 계획 기록(기록장)
- 지금 가격의 위치(고점 대비·이동평균 대비)
- 재무 상태·수급 흐름 표시

</td>
<td width="50%" valign="top">

### ❌ 하지 않습니다 — 예측

- 오를지 내릴지 맞히기
- 매수·매도 추천
- 목표가·확률·등급 제시
- 자동매매

한국 대형주로 직접 검증해 봤지만
**비용을 빼고 나면 통계적으로 유의한
가격 예측 신호를 찾지 못했습니다.**
그래서 그 자리를 비워 두었습니다.

</td>
</tr>
</table>

<br>

## 검증을 어떻게 했나

신호를 넣기 전에 통과해야 하는 절차를 먼저 만들었고, **결과가 나쁘면 기능을 뺐습니다.**

| 항목 | 방법 |
|---|---|
| 예측력 측정 | 횡단면 Rank IC · Newey–West t (lag = 예측지평) |
| 신뢰구간 | 블록 부트스트랩 · 순열검정 |
| 다중검정 보정 | Benjamini–Hochberg FDR · Deflated Sharpe Ratio |
| 표본 분리 | 70/30 홀드아웃 |
| 생존편향 제거 | KRX 시점정합(point-in-time) 유니버스 · 상장폐지 수익률 반영 |
| 비용 반영 | 2026년 거래세(매도 0.20%) + 호가단위 스프레드, 유동성 등급별 |

**결과**: 유효검정수 40·20 어느 기준으로도 **통과한 신호 0개**. Deflated Sharpe도 두 전략 모두 탈락.
표본 8년으로는 연 샤프 0.71 이상만 탐지 가능하다는 사전 검토와 일치했습니다.

발견한 것들도 기록해 둡니다 — 60일 신고가 근접 지표는 상장폐지 종목을 포함하면 t=4.3으로 강력해 보이지만,
생존 종목만 보면 t≈0입니다. **죽어가는 종목이 만들어낸 착시**였습니다.

<br>

## 설치

```bash
git clone https://github.com/tenkojun/nao-stock.git
cd nao-stock
pip install flask numpy requests pandas finance-datareader pywebview
```

`나오주식_실행.bat`을 한 번 실행하면 필요한 라이브러리를 설치하고
**바탕화면에 아이콘을 만들어 줍니다.** 다음부터는 아이콘만 누르면 됩니다.

주소창도, 탭도, 검은 명령창도 뜨지 않습니다 — 자체 창으로 열립니다.

```bash
pythonw 나오주식.pyw     # 프로그램 창으로 실행
python server.py         # 개발용(브라우저, 자동 리로드)
python tools/check.py    # 배포 전 점검
```

시세를 보려면 한국투자증권 OpenAPI 키가 필요합니다.
프로그램의 **설정 → API 연결**에서 입력해 저장할 수 있습니다.
키가 없어도 화면은 합성 데이터로 동작합니다.

<br>

## 구조

```
나오주식.pyw          프로그램 런처 (pywebview 자체 창)
server.py             Flask 백엔드 · REST API
index.html            단일 화면 UI (Lightweight Charts)
engine/
  analyze.py            종목 분석 파이프라인
  kis_kr.py             한국투자증권 실시간 시세·투자자별 수급
  krx_api.py            KRX 시점정합 유니버스
  costs.py              세금·스프레드 왕복비용
  allocate.py           여윳돈 배분 계산
  journal.py            매매 기록장
  validate.py           검증 하네스
  multiple_testing.py   BH-FDR · Deflated Sharpe
  signal_engine/        근거 등록·신뢰도·충돌 해소
tools/check.py        배포 전 자동 점검
```

<br>

## 기술

`Python` · `Flask` · `NumPy` · `pywebview` · `TradingView Lightweight Charts`
데이터: 한국투자증권 OpenAPI · KRX 정보데이터시스템 · FinanceDataReader

<br>

---

<div align="center">

**개발** 정준화 · [tenkojun](https://github.com/tenkojun)

<sub>이 프로그램은 정보 제공용입니다. 투자 판단과 그 결과는 이용자 본인에게 있습니다.</sub>

<sub>MIT License</sub>

</div>
