# BakeOven

烘焙占炉排程：发酵+烘烤半开区间占用炉位，出炉后按炉登记冷却尾段继续占炉，冲突检测与下一可开工窗口。

## 启动

```bash
docker compose up --build
```

| 服务 | 地址 |
| --- | --- |
| 前端 | http://localhost:4500 |
| API | http://localhost:9500 |
| API 文档 | http://localhost:9500/docs |
| Postgres | localhost:5446 |

健康检查：`GET http://localhost:9500/api/health`

## 页面

- `/products` — 产品
- `/ovens` — 炉位
- `/batches` — 批次
- `/gantt` — 甘特
- `/conflicts` — 冲突
- `/windows` — 可开工

## 使用说明

1. 查看产品配方时长与炉位；在炉位页为每座炉登记出炉冷却分钟。
2. 创建生产批次，系统按半开区间占炉并检测冲突；烘烤结束后的冷却尾段继续占住该炉，与下一批发酵/烘烤重叠即记“冷却冲突”（含冷却起止）。冷却为 0 时，下一批可紧接烘烤结束端点排入。
3. 甘特用单独色条画出冷却；可开工窗口把冷却尾计入忙碌，不会把冷却段推荐成空档。

## 开发与测试

```bash
docker compose exec api pytest -q
```
