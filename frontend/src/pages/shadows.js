        import {workspace} from '../workspace.js';

        const page = {
  "title": "换曲线前的跟跑批次",
  "module": "曲线跟跑",
  "caption": "曲线跟跑",
  "detail": "复核员选定弯模、现用版、候选版和观察单数后开批。排位时填炉温、片厚和目标弯度，按现用版验行程并同时封存两版预测；签回填实弯。收足观察单后用同批实弯比较两版平均绝对误差，候选更准才接替现用版。",
  "path": "/shadows",
  "columns": [
    {
      "name": "code",
      "label": "批次"
    },
    {
      "name": "jig",
      "label": "弯模"
    },
    {
      "name": "current_profile",
      "label": "现用版"
    },
    {
      "name": "candidate_profile",
      "label": "候选版"
    },
    {
      "name": "target_count",
      "label": "观察单数"
    },
    {
      "name": "collected",
      "label": "已收单"
    },
    {
      "name": "state",
      "label": "状态"
    },
    {
      "name": "current_mae",
      "label": "现用版 MAE mm"
    },
    {
      "name": "candidate_mae",
      "label": "候选版 MAE mm"
    },
    {
      "name": "decision",
      "label": "收尾结论"
    }
  ],
  "layout": "stack",
  "view": "table",
  "actions": [
    {
      "name": "open_run",
      "label": "开一批跟跑",
      "path": "/shadows/open-run",
      "fields": [
        {
          "name": "code",
          "label": "批次编号",
          "kind": "text",
          "initial": "SHD-02"
        },
        {
          "name": "jig",
          "label": "弯模",
          "kind": "text",
          "initial": "CL-44"
        },
        {
          "name": "current_profile",
          "label": "现用版",
          "kind": "text",
          "initial": "PRO-11"
        },
        {
          "name": "candidate_profile",
          "label": "候选版",
          "kind": "text",
          "initial": "PRO-30"
        },
        {
          "name": "target_count",
          "label": "观察单数",
          "kind": "int",
          "initial": 3
        }
      ],
      "help": "现用版须与该弯模在役版本一致；同一弯模同时只开一批。",
      "roles": [
        "reviewer"
      ],
      "success": "已写入"
    },
    {
      "name": "book_order",
      "label": "排一张跟跑单",
      "path": "/shadows/book-order",
      "fields": [
        {
          "name": "run",
          "label": "批次编号",
          "kind": "text",
          "initial": "SHD-01"
        },
        {
          "name": "code",
          "label": "跟跑单编号（可空）",
          "kind": "text",
          "initial": ""
        },
        {
          "name": "heat",
          "label": "炉温 °C",
          "kind": "float",
          "initial": 500
        },
        {
          "name": "thick",
          "label": "片厚 mm",
          "kind": "float",
          "initial": 4
        },
        {
          "name": "target",
          "label": "目标弯度 mm",
          "kind": "float",
          "initial": 10
        }
      ],
      "help": "按现用版验行程，同时封存两版对该工况的预测；停排的单不占观察单数。",
      "roles": [
        "operator",
        "reviewer"
      ],
      "success": "已写入"
    },
    {
      "name": "sign_order",
      "label": "签回实弯",
      "path": "/shadows/sign-order",
      "fields": [
        {
          "name": "order",
          "label": "跟跑单编号",
          "kind": "text",
          "initial": "SH-03"
        },
        {
          "name": "measured",
          "label": "实弯 mm",
          "kind": "float",
          "initial": 7.3
        }
      ],
      "help": "一张单只计一次；重试不会重复计入观察单数。收足后自动比较两版并给出结论。",
      "roles": [
        "reviewer"
      ],
      "success": "已签回"
    }
  ]
};

        const orderColumns = [
          {"name": "code", "label": "跟跑单"},
          {"name": "run", "label": "批次"},
          {"name": "heat", "label": "炉温 °C"},
          {"name": "thick", "label": "片厚 mm"},
          {"name": "target", "label": "目标弯度 mm"},
          {"name": "current_prediction", "label": "现用版预测 mm"},
          {"name": "candidate_prediction", "label": "候选版预测 mm"},
          {"name": "measured", "label": "实弯 mm"},
          {"name": "state", "label": "状态"}
        ];

        export const {title} = page;
        export const key = "shadows";
        page.secondary = {"caption": "跟跑单与封存预测", "path": "/shadows/orders", "columns": orderColumns, "view": "table"};
        export async function render(root, role) {
          await workspace(root, role, page);

        }
