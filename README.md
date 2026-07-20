# B站视频播放量监控系统

## 功能
- 通过企微群机器人发送 BV号 添加监控
- 每2小时自动检查播放量
- 达到8w阈值即企微播报
- 达标后自动移除监控

## 架构
- Cloudflare Worker: 接收企微消息回调
- GitHub Actions: 定时检查播放量

## 命令
- 添加 BV1xxxxxxxxx
- 列表
- 移除 BV1xxxxxxxxx
