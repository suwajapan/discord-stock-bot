# Discord 日本株市況Bot

毎朝9:30（JST）に日経平均・TOPIXなどの日本株指数をDiscordに自動投稿するBotです。

## 機能

- 日経平均（^N225）とTOPIX（^TOPX）の市況情報を取得
- 始値、前日終値、変動幅・変動率を表示
- 土日は自動でスキップ

## セットアップ

### 1. Discord Webhookの作成

1. Discordで投稿先のサーバーを開く
2. サーバー設定 → 連携サービス → Webhook
3. 「新しいウェブフック」をクリック
4. 投稿先チャンネルを選択
5. 「ウェブフックURLをコピー」でURLを取得

### 2. GitHubリポジトリの設定

1. このリポジトリをGitHubにpush
2. リポジトリの Settings → Secrets and variables → Actions
3. 「New repository secret」をクリック
4. Name: `DISCORD_WEBHOOK_URL`
5. Value: 上記で取得したWebhook URL
6. 「Add secret」をクリック

### 3. 動作確認

1. リポジトリの Actions タブを開く
2. 「Daily Stock Report」ワークフローを選択
3. 「Run workflow」ボタンをクリックして手動実行
4. Discordに投稿されることを確認

## ローカルでのテスト

```bash
# 依存パッケージのインストール
pip install -r requirements.txt

# 環境変数を設定して実行
export DISCORD_WEBHOOK_URL="your_webhook_url_here"
python main.py
```

## カスタマイズ

`main.py` の `INDICES` 辞書を編集することで、監視する指数を変更できます。

```python
INDICES = {
    "^N225": "日経平均",
    "^TOPX": "TOPIX",
    # 他の指数を追加可能
}
```

## スケジュール

GitHub Actionsにより、毎朝9:30 JST（月〜金）に自動実行されます。
