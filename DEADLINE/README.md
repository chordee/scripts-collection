# Deadline Tools

Deadline Monitor 用的輔助腳本。

## 目錄結構

```text
DEADLINE/
└── scripts/
    ├── Jobs/
    │   ├── CopyJobsIdAsText.py         複製所選 Job ID（空白分隔）
    │   └── CopyJobsIdAsJson.py         複製所選 Job ID（JSON）
    └── Tasks/
        ├── CopyJobIdAndTasksIdAsText.py  複製 Job ID + Task index（空白分隔）
        └── CopyJobIdAndTasksIdAsJson.py  複製 Job ID + Task index（JSON）
```

## 安裝

將 `scripts/Jobs/` 與 `scripts/Tasks/` 下的檔案複製到 Deadline Repository 的對應目錄：

```text
<DeadlineRepository>/custom/scripts/Jobs/
<DeadlineRepository>/custom/scripts/Tasks/
```

重啟 Deadline Monitor（或 Tools > Reload Repository Scripts）後，在 Job / Task Panel 右鍵 > Scripts 即可看到。

## 腳本說明

### Jobs

| 腳本 | 輸出範例 |
|---|---|
| `CopyJobsIdAsText` | `a1b2c3d4 e5f6a7b8` |
| `CopyJobsIdAsJson` | `{"deadline_renderfarm_manager":{"job_id":["a1b2c3d4","e5f6a7b8"]}}` |

- 多選時所有 Job ID 一起輸出

### Tasks

| 腳本 | 輸出範例 |
|---|---|
| `CopyJobIdAndTasksIdAsText` | `a1b2c3d4 0 1 5` |
| `CopyJobIdAndTasksIdAsJson` | `{"deadline_renderfarm_manager":{"job_id":"a1b2c3d4","task_ids":[0,1,5]}}` |

- `job_id`：所屬 Job 的 ID（字串）
- `task_ids`：選取 Task 的 0-based index，非 frame number

所有輸出皆為單行，複製後可直接貼到終端或腳本中使用。
