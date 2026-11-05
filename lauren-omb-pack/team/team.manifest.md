# team.manifest（Team 产品线）

显示名（OMB 侧栏）：幕僚长 / 云端编程助手 / 验证助手 / Nancy私人助理 / 工程主管Matcha / 工程bot① / 工程bot②  
技术 key 不变：

- chief / developer / verifier → **Team 专用指令** `bots/chief|developer|verifier/`（及 flat `*.instructions.md`；与 Lite 根包职责同源、**profile 不同**）
- nancy → bots/nancy.instructions.md (+ bots/nancy/SOUL.md)
- matcha → bots/matcha.instructions.md (+ bots/matcha/SOUL.md)
- eng-a / eng-b → **拆解转交中间层**（本期不做业务实现；永不写业务代码；③④未建）
- group → groups/lauren-team.md（可选；优先私聊幕僚长）
- 导入文件：`lauren-team.botmrr.md`（+ `team.mausteam.json`）
- 路由口径：**原图核心链 `engineering_chain`（默认）+ 可选捷径 `fast_path`（默认关）**
- 与 Lite 根包平行；不把 Nancy / Matcha 写进 Lite 根目录
