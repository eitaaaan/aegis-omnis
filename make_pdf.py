from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfWriter, PdfReader

pdfmetrics.registerFont(TTFont("NotoSans", "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf"))
pdfmetrics.registerFont(TTFont("NotoSansBold", "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf"))

W, H = A4
M = 20 * mm

def make_style(name, font="NotoSans", size=10, leading=16, color=colors.black, bold=False, space_before=0, space_after=4):
    return ParagraphStyle(name, fontName="NotoSansBold" if bold else "NotoSans", fontSize=size, leading=leading, textColor=color, spaceAfter=space_after, spaceBefore=space_before)

DARK=colors.HexColor("#1a1a2e"); ACCENT=colors.HexColor("#4f8ef7"); LIGHT=colors.HexColor("#f0f4ff"); GRAY=colors.HexColor("#666666"); BORDER=colors.HexColor("#ccddff")
s_title=make_style("title",size=20,leading=28,color=DARK,bold=True,space_after=2); s_sub=make_style("sub",size=11,leading=16,color=GRAY,space_after=10)
s_h1=make_style("h1",size=13,leading=18,color=ACCENT,bold=True,space_before=12,space_after=4); s_h2=make_style("h2",size=11,leading=16,color=DARK,bold=True,space_before=8,space_after=3)
s_body=make_style("body",size=9.5,leading=15,color=colors.HexColor("#333333"),space_after=3); s_label=make_style("label",size=8.5,leading=13,color=GRAY)
s_tag=make_style("tag",size=9,leading=14,color=ACCENT,bold=True)

def info_table(rows):
    data=[[Paragraph(k,s_label),Paragraph(v,s_body)] for k,v in rows]
    return Table(data,colWidths=[35*mm,W-2*M-35*mm],style=TableStyle([("BACKGROUND",(0,0),(0,-1),LIGHT),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5),("LEFTPADDING",(0,0),(-1,-1),6),("RIGHTPADDING",(0,0),(-1,-1),6),("GRID",(0,0),(-1,-1),0.3,BORDER),("ROWBACKGROUNDS",(1,0),(1,-1),[colors.white,colors.HexColor("#f8faff")])]))

def section_table(headers,rows,col_widths):
    data=[[Paragraph(h,make_style("th",size=8.5,bold=True,color=colors.white)) for h in headers]]
    for row in rows: data.append([Paragraph(c,s_body) for c in row])
    return Table(data,colWidths=col_widths,style=TableStyle([("BACKGROUND",(0,0),(-1,0),ACCENT),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,colors.HexColor("#f0f4ff")]),("GRID",(0,0),(-1,-1),0.3,BORDER),("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4),("LEFTPADDING",(0,0),(-1,-1),6),("RIGHTPADDING",(0,0),(-1,-1),6),("VALIGN",(0,0),(-1,-1),"TOP")]))

def arrow(): return Paragraph("▼",make_style("arr",size=10,color=ACCENT,space_before=2,space_after=2))

def flow_box(text,bg,fg=colors.white,bold=True):
    style=make_style("fb",size=9,leading=14,color=fg,bold=bold)
    return Table([[Paragraph(text,style)]],colWidths=[W-2*M],style=TableStyle([("BACKGROUND",(0,0),(-1,-1),bg),("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6),("LEFTPADDING",(0,0),(-1,-1),10),("RIGHTPADDING",(0,0),(-1,-1),10)]))

story1=[]
story1.append(Paragraph("Project Aegis - 哲学的解消",s_title))
story1.append(Paragraph("S-01 Aegis Omnis v130.4 | LLMローカルAIアシスタント",s_sub))
story1.append(HRFlowable(width="100%",thickness=1.5,color=ACCENT,spaceAfter=12))
story1.append(Paragraph("企画背景・コンセプト",s_h1))
story1.append(Paragraph("後期ウィトゲンシュタインは「哲学的問題は言語の誤用から生まれる、日常言語に戻せば解消できる」と説いた。この思想をAIアシスタントの設計思想として体現することを目的とし、難解な技術・概念を日常言語に翻訳するローカルAIアシスタントを開発した。プログラミング未経験の状態からAIコーディング（Claude / Anthropic 無料枠 + Gemini 無料枠）のみを使用し、環境構築から現バージョンまで25日で開発。",s_body))
story1.append(Paragraph("プロジェクト概要",s_h1))
story1.append(info_table([("プロジェクト名","Project Aegis - S-01 Aegis Omnis v130.4"),("開発体制","個人開発"),("開発期間","25日（環境構築含む、現在も継続開発中）"),("開発手法","AIコーディング（Claude / Anthropic 無料枠 + Gemini 無料枠）のみ使用、プログラミング未経験から開始"),("到達フェーズ","ローカル環境での運用中（継続開発中）"),("総コード量","11,000行超（Pythonシングルファイル）"),("バックエンド","Ollama（gemma3:1b / 4b / 12b）"),("動作環境","Ryzen 7 5700U / RAM 32GB（CPUオンリー、クラウド不使用）")]))
story1.append(Spacer(1,6))
story1.append(Paragraph("主要機能",s_h1))
story1.append(Paragraph("① 5段階 Advanced RAG パイプライン",s_h2))
story1.append(section_table(["ステップ","技術","役割"],[["① HyDE","クエリ拡張","質問を「答えっぽい文章」に変換してからベクトル検索（精度向上）"],["② ベクトル検索","ChromaDB","意味の近さで関連情報を取得"],["③ キーワード検索","BM25","キーワード一致で関連情報を取得"],["④ 結果融合","RRF (k=60)","②と③の検索結果を論文推奨値で融合"],["⑤ 再ランキング","Cross-Encoder","ms-marco-MiniLM-L-6-v2で最終スコアリング"]],[22*mm,28*mm,W-2*M-50*mm]))
story1.append(Spacer(1,4))
story1.append(Paragraph("② モデル自動3段階選択",s_h2))
story1.append(Paragraph("質問の複雑度・長さを推定し、gemma3:1b（高速）/ 4b（標準）/ 12b（高精度）を動的に切り替え。CPU環境での応答速度と精度を最適化。",s_body))
story1.append(Paragraph("③ ゲームAI",s_h2))
story1.append(section_table(["ゲーム","アルゴリズム","UI"],[["将棋","Negamax + TranspositionTable + KillerHeuristic","cursesターミナルUI"],["チェス","MCTS（モンテカルロ木探索）","cursesターミナルUI"],["麻雀","役・符計算完全実装、3人/4人対応","ブラウザHTML自動生成"]],[22*mm,65*mm,W-2*M-87*mm]))
story1.append(Spacer(1,4))
story1.append(Paragraph("④ その他主要機能",s_h2))
story1.append(section_table(["機能","概要"],[["哲学者ペルソナ36人","ソクラテス〜ロールズ。前期・後期ウィトゲンシュタインを別ペルソナとして実装"],["自己最適化エンジン","120秒ごとに会話ログを5軸自己評価し、プロンプトを自動改善"],["ReActエージェント","Web検索・計算・ファイル操作を並列実行（asyncio）"],["語源図鑑 /ety","100種以上の補正辞書でハルシネーション抑制"],["MIDI/画像/TTS生成","テーマからMIDI生成、PIL数学アート生成、音声読み上げ"]],[40*mm,W-2*M-40*mm]))
story1.append(Spacer(1,8))
story1.append(Paragraph("成果・課題",s_h1))
story1.append(info_table([("成果","未経験25日でLLMアプリとしての主要機能（RAG・エージェント・ゲームAI）を単一ファイルに統合。ローカル環境で安定動作を確認。"),("課題","現在はCPUのみ対応。GPU対応・クラウド化・フロントエンドUI実装を次フェーズとして検討中。"),("継続開発","v130.4現在も機能追加・最適化を継続中。")]))
doc1=SimpleDocTemplate("/home/kouta/aegis_system/page1.pdf",pagesize=A4,leftMargin=M,rightMargin=M,topMargin=M,bottomMargin=M)
doc1.build(story1)
print("Page 1 done")

story2=[]
story2.append(Paragraph("アーキテクチャ概要",s_title))
story2.append(Paragraph("S-01 Aegis Omnis v130.4 - システム構成",s_sub))
story2.append(HRFlowable(width="100%",thickness=1.5,color=ACCENT,spaceAfter=12))
story2.append(Paragraph("システム構成図（処理フロー）",s_h1))
story2.append(flow_box("【入力】ユーザーテキスト / コマンド (/a /s /chess /mj ...)",ACCENT))
story2.append(arrow())
story2.append(flow_box("【入力処理層】sanitize() → normalize() → プロンプトインジェクション多層防御\n  Layer1: XMLタグ無効化  Layer2: 役割変更パターン除去  Layer3: ゼロ幅文字除去",colors.HexColor("#5c6bc0")))
story2.append(arrow())
story2.append(flow_box("【複雑度推定 & モデル選択】estimate_complexity()\n  → gemma3:1b（挨拶・短文）/ 4b（標準）/ 12b（哲学・長文・deep思考）",colors.HexColor("#7b8fd4")))
story2.append(arrow())

col_w=(W-2*M-8*mm)/3
def col_box(title,body,bg_h,bg_b):
    return Table([[[Paragraph(title,make_style("ch",size=8.5,bold=True,color=colors.white))],[Paragraph(body,make_style("cb",size=8,leading=13,color=DARK))]],],colWidths=[col_w],style=TableStyle([("BACKGROUND",(0,0),(-1,0),bg_h),("BACKGROUND",(0,1),(-1,-1),bg_b),("TOPPADDING",(0,0),(-1,-1),5),("BOTTOMPADDING",(0,0),(-1,-1),5),("LEFTPADDING",(0,0),(-1,-1),6),("RIGHTPADDING",(0,0),(-1,-1),6),("GRID",(0,0),(-1,-1),0.3,BORDER)]))

three_col=Table([[
    col_box("RAG パイプライン","① HyDE クエリ拡張\n② ChromaDB ベクトル検索\n③ BM25 キーワード検索\n④ RRF融合 (k=60)\n⑤ Cross-Encoder Rerank\n⑥ Web検索 / ローカルKB",colors.HexColor("#1565c0"),colors.HexColor("#e8f0fe")),
    col_box("会話 & ペルソナ層","哲学者ペルソナ 36人\nThinking Mode\nTokenBudget管理\n自己評価 (5軸スコア)\nプロンプト自動最適化\nユーザー指摘即時反映",colors.HexColor("#6a1b9a"),colors.HexColor("#f3e5f5")),
    col_box("ゲーム & ツール層","将棋AI: Negamax+TT+Killer\nチェスAI: MCTS\n麻雀: HTML自動生成\nReActエージェント\nMIDI/画像/TTS生成\nSPI対策機能",colors.HexColor("#b71c1c"),colors.HexColor("#fce4ec")),
]],colWidths=[col_w,col_w,col_w],style=TableStyle([("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),0),("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(0,-1),4),("RIGHTPADDING",(1,0),(1,-1),4),("RIGHTPADDING",(2,0),(2,-1),0)]))
story2.append(three_col)
story2.append(arrow())
story2.append(flow_box("【BackgroundOptimizer】120秒間隔\n  RAGキャッシュ管理 / 温度自動調整 / プロンプト改善 / 学習データ保存",colors.HexColor("#e65100")))
story2.append(arrow())
story2.append(flow_box("【出力 & 永続化】ストリーミング出力 → ChromaDB / s01_state.json / 会話履歴",colors.HexColor("#2e7d32")))
story2.append(Spacer(1,10))
story2.append(Paragraph("セキュリティ・運用の工夫",s_h1))
story2.append(section_table(["カテゴリ","実装内容"],[["プロンプトインジェクション防御","3層防御: XMLタグ無効化 / 役割変更パターン正規表現除去 / ゼロ幅文字除去（Layer3先行実行でバイパス対策）"],["SSRF防御","プライベートIPレンジ全域 + IPv6マップドアドレス（::ffff:127.x.x.x）まで検査。リダイレクト先も再検査。"],["ASTベース電卓","astモジュールでホワイトリスト外ノードを拒否。type()・repr()も除外。eval()不使用。"],["スレッドセーフ設計","TEMP_VOICE / ベクトルDB辞書 / IDインクリメント / HyDEキャッシュに全てthreading.Lockを適用。"],["速度最適化 (v130.4)","num_ctx半減 / RAGプリフェッチ / HyDE並列化 / 8文字バッファ書き出し など11項目。"]],[38*mm,W-2*M-38*mm]))
story2.append(Spacer(1,6))
story2.append(Paragraph("技術スタック",s_h1))
story2.append(section_table(["領域","技術・ライブラリ"],[["LLMバックエンド","Ollama (gemma3:1b/4b/12b)"],["ベクトルDB","ChromaDB"],["RAG","BM25 (rank-bm25), sentence-transformers (Cross-Encoder), HyDE"],["ゲームAI","Negamax, MCTS, curses（将棋・チェス）, HTML生成（麻雀）"],["並列処理","asyncio, threading, ThreadPoolExecutor"],["動作環境","Ryzen 7 5700U / RAM 32GB / CPUオンリー / クラウド不使用"]],[30*mm,W-2*M-30*mm]))

doc2=SimpleDocTemplate("/home/kouta/aegis_system/page2.pdf",pagesize=A4,leftMargin=M,rightMargin=M,topMargin=M,bottomMargin=M)
doc2.build(story2)
print("Page 2 done")

writer=PdfWriter()
for f in ["/home/kouta/aegis_system/page1.pdf","/home/kouta/aegis_system/page2.pdf"]:
    for page in PdfReader(f).pages:
        writer.add_page(page)
with open("/home/kouta/aegis_system/ProjectAegis.pdf","wb") as out:
    writer.write(out)
print("完成: ProjectAegis.pdf")
