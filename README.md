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

## 무엇을 근거로 만들었나

화면에 올린 지표에는 전부 출처가 있습니다. 다만 **논문이 있다는 것과 한국 시장에서 돈이 된다는 것은 다른 문제**라,
각 항목에 근거의 세기를 등급으로 붙이고 앱 안에서도 그대로 보여줍니다.

`A` 강한 실증 · `B` 실무·논쟁 · `C` 약함 · `V` 한국 데이터로 자체검증

| | 근거 논문 | 어디에 쓰나 |
|:--:|---|---|
| `A` | **A Simple Long Memory Model of Realized Volatility** — Corsi (2009), *J. of Financial Econometrics* · [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=626064) | HAR-RV 예상 변동폭 밴드 |
| `A` | **Illiquidity and Stock Returns** — Amihud (2002), *J. of Financial Markets* · [DOI](https://doi.org/10.1016/S1386-4181(01)00024-6) | 유동성 위험 — 팔고 싶을 때 못 파는 종목 |
| `A` | **What Do We Know About the Profitability of Technical Analysis?** — Park & Irwin (2007), *J. of Economic Surveys* · [DOI](https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1467-6419.2007.00519.x) | 손익분기 비용 0.22~0.39% — 비용 기준선 |
| `V` | **Returns to Buying Winners and Selling Losers** — Jegadeesh & Titman (1993), *J. of Finance* · [JSTOR](https://www.jstor.org/stable/2328882) | 중기 모멘텀 — 한국 250종목 재검증 |
| `B` | **The Cross-Section of Expected Stock Returns** — Fama & French (1992), *J. of Finance* · [DOI](https://doi.org/10.1111/j.1540-6261.1992.tb04398.x) | 가치 지표(PBR) 해석 |
| `B` | **The Other Side of Value: Gross Profitability** — Novy-Marx (2013), *J. of Financial Economics* · [DOI](https://doi.org/10.1016/j.jfineco.2013.01.003) | 퀄리티 — 사업의 체력 |
| `B` | **Do Foreign Investors Destabilize Stock Markets?** — Choe, Kho & Stulz (1999), *J. of Financial Economics* · [DOI](https://doi.org/10.1016/S0304-405X(99)00037-9) | 외국인·기관 수급 해석 (한국 시장 연구) |
| `B` | **The Total Cost of Transactions on the NYSE** — Berkowitz, Logue & Noser (1988), *J. of Finance* · [DOI](https://doi.org/10.1111/j.1540-6261.1988.tb04593.x) | VWAP — 집행 기준선 |
| `B` | **Momentum Crashes** — Daniel & Moskowitz (2016), *J. of Financial Economics* · [DOI](https://doi.org/10.1016/j.jfineco.2015.12.002) | 모멘텀이 무너지는 국면 경고 |
| `C` | **Evidence of Predictable Behavior of Security Returns** — Jegadeesh (1990), *J. of Finance* · [DOI](https://doi.org/10.1111/j.1540-6261.1990.tb05110.x) | 단기 반전 — 약해서 참고 관찰로만 |

<br>

## 어떻게 검증했나

"백테스트가 잘 나왔다"는 말은 근거가 되지 못합니다. 충분히 많은 조합을 시험하면
아무 의미 없는 규칙에서도 좋은 성적이 나오기 때문입니다.
그래서 **신호를 넣기 전에 통과해야 할 절차를 먼저 정해 두고**, 결과가 나쁘면 기능을 뺐습니다.

| 단계 | 방법 | 출처 |
|---|---|---|
| 예측력 측정 | 횡단면 Rank IC | Fama & MacBeth (1973) 계열 |
| 자기상관 보정 | Newey–West t (lag = 예측지평) | [Newey & West (1987)](https://doi.org/10.2307/1913610) |
| 신뢰구간 | 블록 부트스트랩 · 순열검정 | [Politis & Romano (1994)](https://doi.org/10.1080/01621459.1994.10476870) |
| 다중검정 보정 | Benjamini–Hochberg FDR | [Benjamini & Hochberg (1995)](https://doi.org/10.1111/j.2517-6161.1995.tb02031.x) |
| 과적합 보정 | Deflated Sharpe Ratio | [Bailey & López de Prado (2014)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551) |
| 유의 기준 | t > 3 (신규 팩터) | [Harvey, Liu & Zhu (2016)](https://doi.org/10.1093/rfs/hhv059) |
| 생존편향 제거 | KRX 시점정합 유니버스 · 상장폐지 수익률 반영 | [Shumway (1997)](https://doi.org/10.1111/j.1540-6261.1997.tb03818.x) |
| 표본 분리 | 70 / 30 홀드아웃 | — |
| 비용 반영 | 거래세(매도 0.20%) + 호가단위 스프레드, 유동성 등급별 | KRX 호가단위 · Park & Irwin (2007) |

<br>

## 그래서 결과는

| 0 | 250 | 8년 | 0.71 |
|:--:|:--:|:--:|:--:|
| 보정 후 통과한 신호 | 검증 종목 | 표본 기간 | 탐지 가능한 최소 연 샤프 |

유효검정수 40·20 어느 기준으로도 **통과한 신호 0개**. Deflated Sharpe도 두 전략 모두 탈락했습니다.
개별 t값이 나온 항목은 있었지만(모멘텀·단기반전), **다중검정 보정과 거래비용을 함께 반영하면 남지 않았습니다.**

> 그래서 이 앱은 가격 신호를 "판정"이 아니라 "관찰"로만 표시합니다.
> 확인되지 않은 것은 확인되지 않았다고 적습니다.

가장 크게 속을 뻔했던 것도 적어 둡니다. 60일 신고가 근접 지표는 상장폐지 종목을 포함해 계산하면 t=4.3으로
아주 강력해 보입니다. 그런데 살아남은 종목만 보면 t≈0입니다. **죽어가는 종목이 만들어낸 착시**였고,
생존편향을 제거하지 않았다면 이 신호를 그대로 넣었을 것입니다.

한국 시장에 대한 기존 연구도 이 결과와 어긋나지 않습니다. Chui, Titman & Wei (2010)는 개인주의 성향이 낮은
시장(한국 포함)에서 모멘텀이 약하거나 반전이 우세하다고 보고합니다
([*J. of Finance*](https://doi.org/10.1111/j.1540-6261.2009.01532.x)).

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
