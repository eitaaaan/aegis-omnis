#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# s01_spi.py — SPI/玉手箱対策・問題生成・採点
from __future__ import annotations
from s01_config import *
from s01_rag import stream_response

# SPI / 玉手箱 対策モジュール
# /spi          ランダム出題（言語+非言語ミックス）
# /spi 言語     言語問題のみ
# /spi 非言語   非言語問題のみ
# /spi 英語     英語問題のみ（玉手箱対策）
# /spi 模擬     10問連続模擬試験モード
# /spi 成績     正答率・カテゴリ別統計
# /spi リセット 成績リセット
# ===================================================================

import random as _random

# ---------- 問題データベース ----------
_SPI_DB: list[dict] = [

    # ===== 言語：語句の意味 =====
    {"cat": "言語", "sub": "語句意味", "q": "「示唆」の意味として最も適切なものを選べ。",
     "choices": ["A: それとなく示すこと", "B: 強く命令すること", "C: 完全に否定すること", "D: 詳しく説明すること"],
     "ans": "A", "exp": "示唆＝それとなくほのめかすこと。suggestに近い。"},

    {"cat": "言語", "sub": "語句意味", "q": "「恣意的」の意味として最も適切なものを選べ。",
     "choices": ["A: 慎重で計画的なさま", "B: 自分の思うままで勝手なさま", "C: 周囲に配慮するさま", "D: 論理的に正確なさま"],
     "ans": "B", "exp": "恣意的＝自分の思いのまま、根拠なく決めること。arbitraryに近い。"},

    {"cat": "言語", "sub": "語句意味", "q": "「逡巡」の意味として最も適切なものを選べ。",
      "choices": ["A: 素早く行動すること", "B: ためらってぐずぐずすること", "C: 激しく怒ること", "D: 深く反省すること"],
     "ans": "B", "exp": "逡巡＝ためらい、なかなか決断できないこと。hesitationに近い。"},

    {"cat": "言語", "sub": "語句意味", "q": "「瑣末」の意味として最も適切なものを選べ。",
     "choices": ["A: 非常に重要なこと", "B: 細かくとるに足らないこと", "C: 複雑に絡み合うこと", "D: 急を要すること"],
     "ans": "B", "exp": "瑣末＝細々としてつまらないこと。trivialに近い。"},

    {"cat": "言語", "sub": "語句意味", "q": "「敷衍」の意味として最も適切なものを選べ。",
     "choices": ["A: 意味を押し広げて詳しく説明すること", "B: 強引に押し通すこと", "C: 簡潔にまとめること", "D: 誤りを訂正すること"],
     "ans": "A", "exp": "敷衍＝内容をひろげてわかりやすく説明すること。elaborateに近い。"},

    # ===== 言語：対義語 =====
    {"cat": "言語", "sub": "対義語", "q": "「促進」の対義語として最も適切なものを選べ。",
     "choices": ["A: 抑制", "B: 継続", "C: 加速", "D: 実行"],
     "ans": "A", "exp": "促進（進める）⇔ 抑制（おさえる）。"},

    {"cat": "言語", "sub": "対義語", "q": "「具体」の対義語として最も適切なものを選べ。",
     "choices": ["A: 現実", "B: 抽象", "C: 詳細", "D: 明確"],
     "ans": "B", "exp": "具体（はっきりしたもの）⇔ 抽象（まとめた概念）。"},

    {"cat": "言語", "sub": "対義語", "q": "「楽観」の対義語として最も適切なものを選べ。",
     "choices": ["A: 慎重", "B: 冷静", "C: 悲観", "D: 否定"],
     "ans": "C", "exp": "楽観（よい方向に考える）⇔ 悲観（悪い方向に考える）。"},

    {"cat": "言語", "sub": "対義語", "q": "「冗長」の対義語として最も適切なものを選べ。",
     "choices": ["A: 簡潔", "B: 詳細", "C: 明瞭", "D: 正確"],
     "ans": "A", "exp": "冗長（余分に長い）⇔ 簡潔（短くまとまっている）。"},

    # ===== 言語：文章整序 =====
    {"cat": "言語", "sub": "文章整序", "q": "次のア〜エを意味が通るよう並べ替えたとき、2番目にくるものを選べ。\nア: しかし、そこには大きな落とし穴がある。\nイ: 効率化は現代のビジネスにおいて最優先事項とされている。\nウ: 人間関係や創造性といった要素が犠牲になりやすいのだ。\nエ: 効率のみを追求すると、",
     "choices": ["A: ア", "B: イ", "C: ウ", "D: エ"],
     "ans": "A", "exp": "イ（主張）→ ア（逆接）→ エ（具体化）→ ウ（結論）の順。2番目はア。"},

    # ===== 非言語：割合・比 =====
    {"cat": "非言語", "sub": "割合", "q": "定価1200円の商品を20%引きで買った。支払い金額はいくらか。",
     "choices": ["A: 900円", "B: 960円", "C: 1000円", "D: 1080円"],
     "ans": "B", "exp": "1200 × (1 - 0.20) = 1200 × 0.80 = 960円。"},

    {"cat": "非言語", "sub": "割合", "q": "ある商品を30%値上げした後、さらに10%値引きした。元の価格と比べて何%の変化か。",
     "choices": ["A: 17%増", "B: 20%増", "C: 23%増", "D: 変化なし"],
     "ans": "A", "exp": "1.30 × 0.90 = 1.17 → 元の価格の117%。つまり17%増。"},

    {"cat": "非言語", "sub": "割合", "q": "原価の40%の利益を見込んで定価をつけた。定価2800円のとき、原価はいくらか。",
     "choices": ["A: 1800円", "B: 2000円", "C: 2100円", "D: 2200円"],
     "ans": "B", "exp": "定価 = 原価 × 1.40 → 原価 = 2800 ÷ 1.40 = 2000円。"},

    # ===== 非言語：速度・距離・時間 =====
    {"cat": "非言語", "sub": "速度", "q": "時速60kmで2時間30分走ったときの距離は何kmか。",
     "choices": ["A: 120km", "B: 140km", "C: 150km", "D: 180km"],
     "ans": "C", "exp": "60 × 2.5 = 150km。2時間30分 = 2.5時間。"},

    {"cat": "非言語", "sub": "速度", "q": "A地点からB地点まで時速40kmで行き、帰りは時速60kmで戻った。平均時速はいくらか。",
     "choices": ["A: 48km/h", "B: 50km/h", "C: 52km/h", "D: 54km/h"],
     "ans": "A", "exp": "往復の平均速度 = 2×40×60÷(40+60) = 4800÷100 = 48km/h。単純平均ではなく調和平均を使う。"},

    {"cat": "非言語", "sub": "速度", "q": "600mの道を歩くと10分かかる。同じ道を自転車では3分でいける。自転車の速さは歩きの何倍か。",
     "choices": ["A: 2倍", "B: 3倍", "C: 3.3倍", "D: 4倍"],
     "ans": "C", "exp": "歩き速度: 600÷10=60m/分。自転車: 600÷3=200m/分。200÷60≒3.3倍。"},

    # ===== 非言語：確率 =====
    {"cat": "非言語", "sub": "確率", "q": "1〜6のサイコロを2回振る。2回とも偶数が出る確率はいくらか。",
     "choices": ["A: 1/6", "B: 1/4", "C: 1/3", "D: 1/2"],
     "ans": "B", "exp": "1回で偶数(2,4,6)が出る確率=3/6=1/2。2回とも: 1/2×1/2=1/4。"},

    {"cat": "非言語", "sub": "確率", "q": "袋の中に赤玉3個・白玉2個がある。2個同時に取り出したとき、2個とも同じ色になる確率はいくらか。",
     "choices": ["A: 2/5", "B: 3/10", "C: 7/10", "D: 4/10"],
     "ans": "A", "exp": "全組合せ: C(5,2)=10。同色: C(3,2)+C(2,2)=3+1=4。確率=4/10=2/5。AとDは同値だがAが正式な既約分数。"},

    {"cat": "非言語", "sub": "確率", "q": "コインを3回投げる。少なくとも1回表が出る確率はいくらか。",
     "choices": ["A: 1/2", "B: 5/8", "C: 7/8", "D: 3/4"],
     "ans": "C", "exp": "1 − (全部裏の確率) = 1 − (1/2)³ = 1 − 1/8 = 7/8。余事象を使うと簡単。"},

    # ===== 非言語：推論・集合 =====
    {"cat": "非言語", "sub": "推論", "q": "「全ての社員はA研修を受けた」「BさんはA研修を受けていない」から確実に言えることを選べ。",
     "choices": ["A: BさんはA研修に合格した", "B: Bさんは社員ではない", "C: 社員はB研修も受けた", "D: BさんはA研修を受けるべきだ"],
     "ans": "B", "exp": "三段論法: 全社員→A研修済。B→A研修未。よってBは社員でない。"},

    {"cat": "非言語", "sub": "集合", "q": "100人のうち英語ができる人60人、中国語ができる人50人、両方できる人20人。どちらもできない人は何人か。",
     "choices": ["A: 10人", "B: 20人", "C: 30人", "D: 40人"],
     "ans": "A", "exp": "英語のみ+中国語のみ+両方 = 40+30+20 = 90人。どちらもできない = 100−90 = 10人。"},

    # ===== 非言語：図表 =====
    {"cat": "非言語", "sub": "図表", "q": "ある会社の売上が2020年100万円、2021年120万円、2022年108万円だった。2021年から2022年の変化率はいくらか。",
     "choices": ["A: −10%", "B: −8%", "C: +8%", "D: +10%"],
     "ans": "A", "exp": "(108−120)÷120 = −12÷120 = −0.10 = −10%。"},

    # ===== 英語（玉手箱） =====
    {"cat": "英語", "sub": "同意語", "q": "「ambiguous」と最も意味が近い語を選べ。",
     "choices": ["A: clear", "B: vague", "C: accurate", "D: simple"],
     "ans": "B", "exp": "ambiguous＝あいまいな。vague（漠然とした）が最も近い。"},

    {"cat": "英語", "sub": "同意語", "q": "「diligent」と最も意味が近い語を選べ。",
     "choices": ["A: lazy", "B: clever", "C: hardworking", "D: quiet"],
     "ans": "C", "exp": "diligent＝勤勉な。hardworking（よく働く）が最も近い。"},

    {"cat": "英語", "sub": "同意語", "q": "「concise」と最も意味が近い語を選べ。",
     "choices": ["A: brief", "B: detailed", "C: complex", "D: extended"],
     "ans": "A", "exp": "concise＝簡潔な。brief（短く要領を得た）が最も近い。"},

    {"cat": "英語", "sub": "同意語", "q": "「inevitable」と最も意味が近い語を選べ。",
     "choices": ["A: avoidable", "B: unexpected", "C: uncertain", "D: unavoidable"],
     "ans": "D", "exp": "inevitable＝避けられない。unavoidable（回避不可能な）が最も近い。"},

    {"cat": "英語", "sub": "英文読解", "q": "次の英文の内容と一致するものを選べ。\n\"The key to effective communication is not just speaking clearly, but also listening actively.\"",
     "choices": ["A: 明確に話すことだけが重要だ", "B: 積極的に聞くことも重要だ", "C: コミュニケーションは話すことで完結する", "D: 聞くことより話すことが優先される"],
     "ans": "B", "exp": "not just A but also B（AだけでなくBも）。listeningも重要と言っている。"},

    # ===== 英語：同意語追加 =====
    {"cat": "英語", "sub": "同意語", "q": "「adequate」と最も意味が近い語を選べ。",
     "choices": ["A: excellent", "B: sufficient", "C: lacking", "D: complex"],
     "ans": "B", "exp": "adequate＝十分な。sufficient（足りている）が最も近い。"},

    {"cat": "英語", "sub": "同意語", "q": "「obsolete」と最も意味が近い語を選べ。",
     "choices": ["A: modern", "B: useful", "C: outdated", "D: popular"],
     "ans": "C", "exp": "obsolete＝時代遅れの・廃れた。outdated（古くなった）が最も近い。"},

    {"cat": "英語", "sub": "同意語", "q": "「transparent」と最も意味が近い語を選べ。",
     "choices": ["A: hidden", "B: clear", "C: heavy", "D: slow"],
     "ans": "B", "exp": "transparent＝透明な・明白な。clear（明確な）が最も近い。"},

    # ===== 玉手箱：四則逆算 =====
    # 形式：□に入る数を選ぶ。速度が命。
    {"cat": "玉手箱", "sub": "四則逆算", "q": "□ × 7 = 56　　□に入る数はいくつか。",
     "choices": ["A: 6", "B: 7", "C: 8", "D: 9"],
     "ans": "C", "exp": "56 ÷ 7 = 8。掛け算の逆算は割り算。"},

    {"cat": "玉手箱", "sub": "四則逆算", "q": "72 ÷ □ = 9　　□に入る数はいくつか。",
     "choices": ["A: 6", "B: 7", "C: 8", "D: 9"],
     "ans": "C", "exp": "72 ÷ 9 = 8。割り算の逆算は割り算（72÷9）。"},

    {"cat": "玉手箱", "sub": "四則逆算", "q": "□ + 47 = 83　　□に入る数はいくつか。",
     "choices": ["A: 34", "B: 36", "C: 38", "D: 40"],
     "ans": "B", "exp": "83 − 47 = 36。足し算の逆算は引き算。"},

    {"cat": "玉手箱", "sub": "四則逆算", "q": "125 − □ = 68　　□に入る数はいくつか。",
     "choices": ["A: 53", "B: 55", "C: 57", "D: 59"],
     "ans": "C", "exp": "125 − 68 = 57。引き算の逆算: □ = 125 − 68。"},

    {"cat": "玉手箱", "sub": "四則逆算", "q": "□ ÷ 6 = 13　　□に入る数はいくつか。",
     "choices": ["A: 72", "B: 78", "C: 80", "D: 84"],
     "ans": "B", "exp": "13 × 6 = 78。割り算の逆算は掛け算。"},

    {"cat": "玉手箱", "sub": "四則逆算", "q": "3 × □ − 5 = 19　　□に入る数はいくつか。",
     "choices": ["A: 6", "B: 7", "C: 8", "D: 9"],
     "ans": "C", "exp": "3×□ = 19+5 = 24 → □ = 24÷3 = 8。後ろから逆算する。"},

    {"cat": "玉手箱", "sub": "四則逆算", "q": "(□ + 4) × 3 = 27　　□に入る数はいくつか。",
     "choices": ["A: 5", "B: 7", "C: 9", "D: 11"],
     "ans": "A", "exp": "□ + 4 = 27÷3 = 9 → □ = 9−4 = 5。括弧の外から逆算。"},

    {"cat": "玉手箱", "sub": "四則逆算", "q": "48 ÷ (□ − 2) = 6　　□に入る数はいくつか。",
     "choices": ["A: 8", "B: 9", "C: 10", "D: 12"],
     "ans": "C", "exp": "□−2 = 48÷6 = 8 → □ = 10。"},

    # ===== 玉手箱：長文一致（一致・不一致・どちらとも言えない の3択） =====
    {"cat": "玉手箱", "sub": "長文一致", "q": (
        "【本文】\n"
        "日本の食品ロスは年間約600万トンとされており、そのうち約半分は家庭から発生している。"
        "食品ロス削減のためには、企業だけでなく消費者一人ひとりの取り組みが不可欠である。\n\n"
        "【設問】「食品ロスの半分以上は企業活動から発生している」\n"
        "本文の内容と比較して、この記述は？"
    ),
     "choices": ["A: 一致する", "B: 一致しない", "C: どちらとも言えない"],
     "ans": "B", "exp": "本文では「約半分は家庭から」とあるため、企業が半分以上というのは不一致。"},

    {"cat": "玉手箱", "sub": "長文一致", "q": (
        "【本文】\n"
        "リモートワークの普及により、都市部から地方への人口移動が緩やかに進んでいる。"
        "ただし、この傾向は主にIT関連職種において顕著であり、全業種への波及は限定的とされる。\n\n"
        "【設問】「IT関連職種ではリモートワークを機に地方移住が進んでいる」\n"
        "本文の内容と比較して、この記述は？"
    ),
     "choices": ["A: 一致する", "B: 一致しない", "C: どちらとも言えない"],
     "ans": "A", "exp": "本文「IT関連職種において顕著」と一致する。"},

    {"cat": "玉手箱", "sub": "長文一致", "q": (
        "【本文】\n"
        "近年、Z世代を中心に「タイパ（タイムパフォーマンス）」を重視する傾向が強まっている。"
        "動画を倍速視聴したり、結末から確認してから作品を観るといった行動がその典型例とされる。\n\n"
        "【設問】「タイパ重視の傾向はすべての世代で同様に見られる」\n"
        "本文の内容と比較して、この記述は？"
    ),
     "choices": ["A: 一致する", "B: 一致しない", "C: どちらとも言えない"],
     "ans": "B", "exp": "本文では「Z世代を中心に」とあり、全世代とは書かれていない。不一致。"},

    {"cat": "玉手箱", "sub": "長文一致", "q": (
        "【本文】\n"
        "再生可能エネルギーの導入コストはこの10年で大幅に低下した。"
        "太陽光発電のコストは2010年比で約80%削減されたとする試算もある。"
        "しかし蓄電技術の課題は依然として残っており、安定供給には課題がある。\n\n"
        "【設問】「蓄電技術の問題が解決されれば再生可能エネルギーは完全に普及する」\n"
        "本文の内容と比較して、この記述は？"
    ),
     "choices": ["A: 一致する", "B: 一致しない", "C: どちらとも言えない"],
     "ans": "C", "exp": "本文は蓄電課題に言及するが、解決後の完全普及については述べていない。「どちらとも言えない」。"},

    # ===== 玉手箱：テーブル問題 =====
    {"cat": "玉手箱", "sub": "テーブル", "q": (
        "下表はA〜C店の月別売上（万円）を示す。\n"
        "┌──────┬────┬────┬────┐\n"
        "│      │ A店 │ B店 │ C店 │\n"
        "├──────┼────┼────┼────┤\n"
        "│ 4月  │ 120 │  90 │ 150 │\n"
        "│ 5月  │ 130 │ 110 │ 140 │\n"
        "│ 6月  │ 110 │ 130 │ 160 │\n"
        "└──────┴────┴────┴────┘\n"
        "3ヶ月の合計売上が最も多い店はどこか。"
    ),
     "choices": ["A: A店", "B: B店", "C: C店", "D: 同じ"],
     "ans": "C", "exp": "A店: 120+130+110=360。B店: 90+110+130=330。C店: 150+140+160=450。C店が最多。"},

    {"cat": "玉手箱", "sub": "テーブル", "q": (
        "下表は社員4人の残業時間（時間/月）を示す。\n"
        "┌──────┬──┬──┬──┬──┐\n"
        "│      │田中│鈴木│佐藤│高橋│\n"
        "├──────┼──┼──┼──┼──┤\n"
        "│ 1月  │ 20 │ 15 │ 30 │ 10 │\n"
        "│ 2月  │ 25 │ 20 │ 20 │ 15 │\n"
        "│ 3月  │ 15 │ 25 │ 25 │ 20 │\n"
        "└──────┴──┴──┴──┴──┘\n"
        "3ヶ月の平均残業時間が最も少ない社員は誰か。"
    ),
     "choices": ["A: 田中", "B: 鈴木", "C: 佐藤", "D: 高橋"],
     "ans": "D", "exp": "田中:60/3=20。鈴木:60/3=20。佐藤:75/3=25。高橋:45/3=15。高橋が最少。"},

    {"cat": "玉手箱", "sub": "テーブル", "q": (
        "下表はある試験の得点分布（人数）を示す。\n"
        "┌──────────┬────┐\n"
        "│ 得点区分   │ 人数 │\n"
        "├──────────┼────┤\n"
        "│ 90点以上   │   5  │\n"
        "│ 70〜89点   │  15  │\n"
        "│ 50〜69点   │  20  │\n"
        "│ 50点未満   │  10  │\n"
        "└──────────┴────┘\n"
        "70点以上の受験者は全体の何%か。"
    ),
     "choices": ["A: 20%", "B: 25%", "C: 40%", "D: 50%"],
     "ans": "C", "exp": "70点以上: 5+15=20人。全体: 5+15+20+10=50人。20÷50=0.40=40%。"},
]

# ---------- 成績管理 ----------
_SPI_SCORE_KEY = "spi_score"

def _spi_load_score() -> dict:
    state = load_state()
    return state.get(_SPI_SCORE_KEY, {"total": 0, "correct": 0, "cats": {}})

def _spi_save_score(sc: dict) -> None:
    state = load_state()
    state[_SPI_SCORE_KEY] = sc
    save_state(state)

def _spi_record(cat: str, correct: bool) -> None:
    sc = _spi_load_score()
    sc["total"] += 1
    if correct: sc["correct"] += 1
    cats = sc.setdefault("cats", {})
    cats.setdefault(cat, {"total": 0, "correct": 0})
    cats[cat]["total"] += 1
    if correct: cats[cat]["correct"] += 1
    _spi_save_score(sc)

# ---------- 出題セッション管理（同一プロセス内） ----------
# セッション状態はload_state()/save_state()で永続化
_SPI_SESSION_KEY = "spi_session"
# ★[修正/spi-3] ファイルI/Oの競合・キャッシュミスによるセッション消失を防ぐため
# メモリ上にもセッションを保持するミラーを追加。
# load/saveは両方に書き込み、loadはメモリを優先して返す。
_SPI_SESSION_MEMORY: dict = {}

def _spi_load_session() -> dict:
    # メモリに有効なセッションがあればそちらを優先（ファイルI/O競合を回避）
    if _SPI_SESSION_MEMORY.get("current") and isinstance(_SPI_SESSION_MEMORY["current"], dict) and len(_SPI_SESSION_MEMORY["current"]) > 0:
        return dict(_SPI_SESSION_MEMORY)
    return load_state().get(_SPI_SESSION_KEY, {
        "current": {}, "mock_queue": [], "mock_results": [], "is_mock": False})

def _spi_save_session(current: dict, queue: list, results: list, is_mock: bool = False) -> None:
    global _SPI_SESSION_MEMORY
    sess = {"current": current, "mock_queue": queue, "mock_results": results, "is_mock": is_mock}
    # メモリに即時反映（ファイル書き込み失敗時のフォールバック）
    _SPI_SESSION_MEMORY = dict(sess)
    state = load_state()
    state[_SPI_SESSION_KEY] = sess
    save_state(state)

def _spi_clear_session() -> None:
    global _SPI_SESSION_MEMORY
    _SPI_SESSION_MEMORY = {}
    state = load_state()
    state.pop(_SPI_SESSION_KEY, None)
    save_state(state)

def _spi_pick(filter_cat: str | None = None) -> dict:
    pool = [q for q in _SPI_DB if filter_cat is None or q["cat"] == filter_cat]
    return _random.choice(pool)

# ---------- 出題履歴管理（ローテーション） ----------
_SPI_USED_IDS: list[str] = []   # 出題済みq_idのリスト（古い順）
_SPI_USED_MAX = 60               # この件数を超えたら古いものを解禁

def _spi_make_id(q: dict) -> str:
    return q.get("q", "")[:30]

def _spi_mark_used(q: dict) -> None:
    qid = _spi_make_id(q)
    if qid in _SPI_USED_IDS:
        _SPI_USED_IDS.remove(qid)
    _SPI_USED_IDS.append(qid)
    if len(_SPI_USED_IDS) > _SPI_USED_MAX:
        _SPI_USED_IDS.pop(0)

def _spi_pick_fresh(filter_cat: str | None = None) -> dict:
    """出題済みを避けてDBから選ぶ。全部出済みならランダム。"""
    pool = [q for q in _SPI_DB if filter_cat is None or q["cat"] == filter_cat]
    fresh = [q for q in pool if _spi_make_id(q) not in _SPI_USED_IDS]
    chosen = _random.choice(fresh) if fresh else _random.choice(pool)
    _spi_mark_used(chosen)
    return chosen

# ---------- LLMによる問題動的生成 ----------
# サブカテゴリ定義（生成指示付き）
_SPI_LLM_SUBTYPES = {
    "言語": [
        ("語句意味",   "「{word}」の意味として最も適切なものを選べ。4択（A/B/C/D）で出題し、正解・不正解の選択肢を作れ。語はSPIで頻出の難読語・ビジネス語から選ぶ。"),
        ("同意語",     "「{word}」と最も意味が近い語を4択で出題せよ。"),
        ("対義語",     "「{word}」の対義語として最も適切な語を4択で出題せよ。"),
        ("文章完成",   "次の文の（　）に入る最も適切な語を4択で選べ。文章はSPIらしい論理的な文にすること。"),
        ("文章整序",   "次のア〜エの文を意味が通る順に並べ替えよ。選択肢は並び順4パターン（A/B/C/D）で出題せよ。"),
        ("長文読解",   "以下の文章を読んで設問に答えよ。本文100字程度・設問は「筆者が述べていること」「本文の内容と一致するもの」等。4択。"),
        ("熟語の意味", "「{word}」の意味として最も適切なものを4択で出題せよ。四字熟語・ことわざ・慣用句から選ぶ。"),
        ("語句用法",   "「{word}」の使い方として正しいものを4択で選べ。誤用しやすい語を選ぶこと。"),
    ],
    "非言語": [
        ("速度・時間・距離", "速さ・時間・距離に関するSPIらしい文章題を1問作れ。4択（A/B/C/D）、数値は整数。"),
        ("割合・比",         "割合や比に関するSPIらしい文章題を1問作れ。4択、数値は整数か単純な小数。"),
        ("損益計算",         "原価・売価・利益率に関するSPIらしい文章題を1問作れ。4択。"),
        ("仕事算",           "AとBが協力して仕事をする問題をSPIらしく作れ。4択。"),
        ("集合・ベン図",     "重複を含む集合（ベン図）の問題をSPIらしく作れ。4択。"),
        ("確率",             "日常的な場面での確率問題をSPIらしく作れ。4択、答えは分数でも可。"),
        ("推論",             "条件が3〜4つ与えられ、正しい結論を選ぶSPI推論問題を作れ。4択。"),
        ("資料解釈",         "表やグラフの数値を読み取る問題をSPIらしく作れ。小さな表（3〜4行）を文章で表現すること。4択。"),
        ("場合の数",         "順列・組み合わせに関するSPIらしい問題を1問作れ。4択。"),
        ("整数・数列",       "規則性のある数列や整数の性質に関するSPI問題を作れ。4択。"),
        ("平均・分散",       "平均・中央値・最頻値に関するSPI問題を作れ。4択。"),
        ("図形・空間",       "図形の面積・体積・角度に関するSPIらしい問題を作れ（図は文章で説明）。4択。"),
    ],
    "玉手箱": [
        ("四則逆算",   "□を含む式（□×n=m、n÷□=m、(□+n)×m=kなど）を作れ。選択肢は整数4択。複合式も含めること。"),
        ("長文一致",   "100〜150字の文章と、その内容についての命題を1つ作れ。選択肢は「A:一致する」「B:一致しない」「C:どちらとも言えない」の3択。"),
        ("テーブル計算","3〜4列・4〜5行の表（売上・在庫・人数等）を文章で与え、合計・差・割合などを問う問題を作れ。4択。"),
        ("図表読取",   "折れ線・棒グラフの数値を文章で表現し、増減・比較・割合を問う問題を作れ。4択。"),
        ("英語語彙",   "TOEIC600〜700点レベルの英単語の意味を問う4択問題を作れ。"),
        ("英文読解",   "3〜4文の短い英文を与え、内容に一致するものを4択で選ばせる問題を作れ。"),
        ("数列完成",   "空欄のある数列（等差・等比・フィボナッチ変形など）の□を埋める問題を作れ。4択。"),
    ],
    "英語": [
        ("語彙",       "TOEIC700点レベルの英単語・熟語の意味を4択で問う問題を作れ。"),
        ("文法",       "英文の空欄に入る最適な語（品詞・前置詞・接続詞等）を4択で選ぶ問題を作れ。"),
        ("読解",       "5〜6文の英文パッセージを書き、内容に関する設問（正誤・主題等）を4択で作れ。"),
        ("語句整序",   "英文の語句を並べ替える問題を作れ。答えは4パターン（A/B/C/D）の並び順。"),
    ],
}

_SPI_LLM_WORDS_LANGUAGE = [
    "逡巡","忖度","蓋然性","漸進","恣意","瑣末","截然","逼迫","敷衍","僭越",
    "矜持","跋扈","遁走","杜撰","慇懃","倦怠","齟齬","乖離","惹起","帰趨",
    "嚆矢","濫觴","淘汰","頑迷","慄然","慄く","邂逅","慷慨","諮問","訓示",
]

def _spi_generate_llm(filter_cat: str | None = None) -> dict | None:
    """LLMでSPI/玉手箱問題を動的生成する。失敗時はNone。"""
    o = _get_ollama()
    if o is None:
        return None

    # カテゴリと出題タイプをランダム選択
    cat = filter_cat if filter_cat else _random.choice(["言語", "非言語", "玉手箱", "英語"])
    subtypes = _SPI_LLM_SUBTYPES.get(cat, _SPI_LLM_SUBTYPES["言語"])
    sub, instruction = _random.choice(subtypes)

    # 言語系は語彙をランダムに差し込む
    word = _random.choice(_SPI_LLM_WORDS_LANGUAGE)
    instruction = instruction.replace("{word}", word)

    sys_prompt = (
        "あなたはSPI・玉手箱の問題作成専門家です。\n"
        "以下の指示に従い、問題を1問だけJSON形式で出力してください。\n"
        "出力形式（必ずこの形式のみ。説明・前置き不要）:\n"
        "{\n"
        '  "q": "問題文（改行は\\nで表現）",\n'
        '  "choices": ["A: 選択肢1", "B: 選択肢2", "C: 選択肢3", "D: 選択肢4"],\n'
        '  "ans": "A",\n'
        '  "exp": "解説文（正解の理由を1〜2文で）"\n'
        "}\n"
        "制約:\n"
        "- 選択肢は必ずA/B/C/Dの4つ（長文一致のみA/B/Cの3つでよい）\n"
        "- 正解は必ず1つ、他は明確に間違い\n"
        "- 数値問題は計算を確認してから出力すること\n"
        "- JSONのみ出力。```json等のマークダウン不要\n"
    )
    user_prompt = f"【カテゴリ】{cat}・{sub}\n【出題指示】{instruction}"

    try:
        raw = ""
        stream = o.chat(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            stream=True,
            options={"temperature": 0.85, "num_predict": 600, "num_ctx": 1024},
        )
        deadline = time.time() + 15.0
        for chunk in stream:
            if time.time() > deadline:
                break
            raw += chunk.get("message", {}).get("content", "")
        # JSONを抽出
        m = re.search(r'\{[\s\S]*\}', raw)
        if not m:
            return None
        data = json.loads(m.group(0))
        # 必須フィールド検証
        if not all(k in data for k in ("q", "choices", "ans", "exp")):
            return None
        if len(data["choices"]) < 3:
            return None
        # 正解が選択肢に含まれているか
        ans = data["ans"].strip().upper()
        if not any(c.startswith(f"{ans}:") for c in data["choices"]):
            return None
        return {
            "cat": cat,
            "sub": f"{sub}★",   # ★=LLM生成を示すマーク
            "q":   data["q"],
            "choices": data["choices"],
            "ans": ans,
            "exp": data["exp"],
        }
    except Exception as e:
        print(f"{C['y']}[SPI-LLM] 生成失敗: {e}{C['w']}")
        return None

def _spi_pick_smart(filter_cat: str | None = None, use_llm: bool = True) -> dict:
    """
    LLM生成を優先し、失敗時はDBからローテーション出題する。
    LLMはバックグラウンドで呼び出し、タイムアウト付き。
    """
    if use_llm:
        result_box: list = []
        def _gen():
            q = _spi_generate_llm(filter_cat)
            if q:
                result_box.append(q)
        t = threading.Thread(target=_gen, daemon=True)
        t.start()
        t.join(timeout=14)   # 最大14秒待つ
        if result_box:
            _spi_mark_used(result_box[0])
            return result_box[0]
    # フォールバック: DBからローテーション
    return _spi_pick_fresh(filter_cat)

def _spi_format_q(q: dict, num: int | None = None) -> str:
    prefix = f"[問{num}] " if num else ""
    header = f"{C['c']}{prefix}【{q['cat']}・{q['sub']}】{C['w']}"
    body   = q["q"]
    choices = "\n".join(q["choices"])
    ans_hint = "A/B/C" if q.get("sub") == "長文一致" else "A/B/C/D"
    return f"{header}\n{body}\n{choices}\n{C['dim']}→ {ans_hint} で答えてください{C['w']}"

def _spi_feedback(q: dict, user_ans: str) -> str:
    """正誤判定＋選択肢付き解説を返す。"""
    correct = user_ans.upper() == q["ans"]
    # 正解の選択肢テキストを取得
    ans_letter = q["ans"]
    ans_text = next((c for c in q["choices"] if c.startswith(f"{ans_letter}:")), ans_letter)
    if correct:
        mark = f"{C['g']}✓ 正解！{C['w']}"
        detail = f"{C['g']}{ans_text}{C['w']}"
    else:
        mark = f"{C['r']}✗ 不正解  あなたの答え: {user_ans.upper()}{C['w']}"
        detail = f"{C['r']}正解 → {ans_text}{C['w']}"
    exp_block = f"{C['c']}【解説】{C['w']} {q['exp']}"
    return correct, f"{mark}\n{detail}\n{exp_block}"

def handle_spi(arg: str) -> str:
    arg = arg.strip()
    _sess = _spi_load_session()
    _spi_current  = _sess["current"]
    _spi_mock_queue   = _sess["mock_queue"]
    _spi_mock_results = _sess["mock_results"]
    _is_mock = _sess.get("is_mock", False)

    # ---------- 答え入力（A/B/C/D） ----------
    if arg.upper() in ("A", "B", "C", "D"):
        # 長文一致は3択なのでDは受け付けない
        if arg.upper() == "D" and _spi_current.get("sub") == "長文一致":
            return f"{C['y']}この問題は A/B/C の3択です。{C['w']}"
        if _is_mock:
            # 模擬試験モード（キューが空でも最終問題として処理）
            q = _spi_current
            if not q:
                return f"{C['y']}問題が出題されていません。/spi 模擬 で開始してください。{C['w']}"
            correct, fb = _spi_feedback(q, arg)
            _spi_record(q["cat"], correct)
            _spi_mock_results.append(correct)
            if _spi_mock_queue:
                _spi_current = _spi_mock_queue.pop(0)
                _spi_save_session(_spi_current, _spi_mock_queue, _spi_mock_results, is_mock=True)
                return f"{fb}\n\n{_spi_format_q(_spi_current, num=len(_spi_mock_results)+1)}"
            else:
                # 模擬試験終了
                total = len(_spi_mock_results)
                ok = sum(_spi_mock_results)
                _spi_save_session({}, [], [], is_mock=False)
                return (f"{fb}\n\n"
                        f"{C['c']}===== 模擬試験終了 ====={C['w']}\n"
                        f"結果: {ok}/{total} 問正解  ({ok*100//total}%)\n"
                        f"/spi 成績 で累計成績を確認できます。")
        else:
            # 通常1問モード
            q = _spi_current
            if not q:
                return f"{C['y']}問題が出題されていません。/spi で問題を出してください。{C['w']}"
            correct, fb = _spi_feedback(q, arg)
            _spi_record(q["cat"], correct)
            # ★[修正/spi-2] セッションクリアは feedback を返した後に確実に実行
            # 旧コードでは save_session({}) が返答前に走りタイミング依存の問題があった
            _spi_save_session({}, [], [], is_mock=False)
            return f"{fb}\n\n次の問題: /spi または /spi [言語/非言語/英語]"

    # ---------- 成績表示 ----------
    if arg in ("成績", "stats", "score"):
        sc = _spi_load_score()
        if sc["total"] == 0:
            return f"{C['y']}まだ解答がありません。/spi で問題を解いてみましょう。{C['w']}"
        pct = sc["correct"] * 100 // sc["total"]
        lines = [f"{C['c']}===== SPI成績 ====={C['w']}",
                 f"総合: {sc['correct']}/{sc['total']} 問正解  ({pct}%)"]
        for cat, v in sc.get("cats", {}).items():
            cpct = v["correct"]*100//v["total"] if v["total"] else 0
            bar = "█" * (cpct//10) + "░" * (10 - cpct//10)
            lines.append(f"  {cat}: {v['correct']}/{v['total']}  [{bar}] {cpct}%")
        return "\n".join(lines)

    # ---------- 成績リセット ----------
    if arg in ("リセット", "reset"):
        state = load_state()
        state.pop(_SPI_SCORE_KEY, None)
        save_state(state)
        _spi_clear_session()
        return f"{C['y']}成績をリセットしました。{C['w']}"

    # ---------- 模擬試験（10問連続） ----------
    if arg in ("模擬", "mock", "test"):
        # DB から5問 + LLMで5問生成（カテゴリ均等）
        cats_cycle = ["言語", "非言語", "玉手箱", "英語", "言語",
                      "非言語", "玉手箱", "英語", "言語", "非言語"]
        _random.shuffle(cats_cycle)
        pool_db = _random.sample(_SPI_DB, min(5, len(_SPI_DB)))
        pool: list[dict] = list(pool_db)  # まずDBの5問を追加

        print(f"{C['dim']}  模擬試験: LLMで問題生成中（5問）…{C['w']}", flush=True)
        for cat_hint in cats_cycle[5:]:   # 残り5問をLLM生成
            q_llm = _spi_generate_llm(cat_hint)
            if q_llm:
                pool.append(q_llm)
            else:
                pool.append(_spi_pick_fresh(cat_hint))  # 失敗時はDBフォールバック

        _random.shuffle(pool)
        pool = pool[:10]
        _spi_mock_queue = pool[1:]
        _spi_mock_results_new = []
        _spi_current = pool[0]
        _spi_save_session(_spi_current, _spi_mock_queue, _spi_mock_results_new, is_mock=True)
        llm_count = sum(1 for p in pool if "★" in p.get("sub", ""))
        return (f"{C['c']}===== 模擬試験開始（10問）====={C['w']}\n"
                f"内訳: DB {10-llm_count}問 + AI生成 {llm_count}問\n"
                f"A/B/C/D で答えてください。\n\n{_spi_format_q(_spi_current, num=1)}")

    # ---------- カテゴリ指定or通常出題 ----------
    cat_map = {"言語": "言語", "非言語": "非言語", "英語": "英語",
               "玉手箱": "玉手箱", "四則逆算": "玉手箱", "長文": "玉手箱", "テーブル": "玉手箱",
               "verbal": "言語", "math": "非言語", "english": "英語", "tama": "玉手箱"}
    filter_cat = cat_map.get(arg) if arg else None
    if arg and filter_cat is None:
        return (f"{C['r']}usage: /spi [言語|非言語|英語|玉手箱|模擬|成績|リセット]\n"
                f"または A/B/C/D で回答{C['w']}")
    with SystemSpinner("SPI問題を生成中…", stage="rag") as _sp:
        q = _spi_pick_smart(filter_cat, use_llm=True)
    _spi_save_session(q, [], [], is_mock=False)
    llm_tag = f" {C['dim']}[AI生成]{C['w']}" if "★" in q.get("sub", "") else ""
    return _spi_format_q(_spi_load_session()["current"]) + llm_tag

# ===== ハンドラ関数群 =====
