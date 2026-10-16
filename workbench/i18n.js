'use strict';
// UI labels only. User annotations, strategy prose and JSON retain their original text.
window.uiLang=localStorage.getItem('lol-workbench-language')==='en'?'en':'zh';
const uiTranslations = new Map([
['LOL 短时补兵决策评估工作台','LOL Short-Window Last-Hit Evaluation Workbench'],
['按完整血条中心记录坐标。蓝红颜色表示阵营；小兵需分别编号。未知内容留空，保存后重新导出表格。','Record complete health-bar centers. Blue/red indicate teams. Give each minion a unique ID. Leave unknowns blank; save and export tables again.'],
['上一帧','Previous frame'],['下一帧','Next frame'],['点击模式','Click mode'],
['当前单位血条中心','Selected unit: health-bar center'],['拖框选完整血条（取中心）','Drag a complete health-bar box (use its center)'],['固定地图纹理原点','Fixed map-texture origin'],
['橙色框仅为颜色填充候选，不能代表完整血条，也没有单位身份。请依据画面手动确认；不使用脚下模型中心。','Orange boxes are colored-fill proposals, not complete bars or unit identities. Confirm visually using the complete bar, not the model beneath it.'],
['左右方向键切帧（输入框内除外）。地图原点必须在各帧追踪同一纹理点，才能扣除镜头平移；同帧单位间距不需要原点。','Use arrow keys outside input fields to change frames. Track the same texture landmark to correct camera translation. Same-frame distances need no origin.'],
['距离小兵 ID（逗号分隔，数量不限；设定沿用至后续帧，直到重新选择）','Minion distance IDs (comma-separated, unlimited; selection persists until changed)'],
['炮车线或兵波重叠时请显式选择','Explicitly select units for cannon or overlapping waves'],
['选取名册内当前全部未确认阵亡的小兵','Select all roster minions not confirmed dead'],['只测英雄之间','Hero-to-hero only'],
['逐项选择距离对象','Select distance targets individually'],['应用勾选对象','Apply checked units'],['单位列表与新增单位','Roster and new units'],
['换波、炮车、召唤物使用新 ID，不能复用已经阵亡单位的 ID。','Use new IDs for later waves, cannons and summons. Never reuse a dead unit ID.'],
['颜色检测不识别炮车或兵种；请人工选择，或导入 AI 已区分兵种的名册。编号由程序生成，不代表自动跟踪到同一只小兵。','Color detection does not classify minions. Select a type or import an AI-reviewed roster. Generated IDs do not imply automatic identity tracking.'],
['留空自动生成永久唯一 ID','Leave blank to generate a permanent unique ID'],['近战 melee','Melee'],['远程 caster','Caster'],['炮车 siege','Siege'],['超级兵 super','Super'],['兵种待确认 minion','Unclassified minion'],['召唤物 summon','Summon'],['加入单位','Add unit'],['当前单位','Selected unit'],
['动作（未知留空）','Action (leave unknowns blank)'],['攻击目标','Attack target'],['攻击相位','Attack phase'],['存活状态','Alive state'],['确认阵亡（此帧起停止记录该单位）','Confirmed dead (stop recording this unit from this frame)'],['未知 / 无目标','Unknown / no target'],['未知','Unknown'],['存活','Alive'],
['生命值或血量比例（口径写备注）','HP or HP fraction (specify convention in notes)'],['动作开始：视频秒数','Action start: source-video seconds'],['动作结束：视频秒数','Action end: source-video seconds'],['备注','Notes'],['记录此帧动作','Record action'],['清除此单位坐标','Clear unit coordinates'],['保存并导出评估包','Save and export assessment bundle'],['已保存。','Saved.'],['保存','Save'],
['导入人工或 AI 标注 JSON','Import manual or AI annotation JSON'],['格式见 docs/workflow.md。导入后覆盖当前标注；先保存备份。','See docs/workflow.md. Import replaces current annotations; back up first.'],['评估预输入','Assessment inputs'],
['距离标尺（像素=游戏单位，空白保留像素）：','Distance calibration (pixels=game units; blank for pixels only):'],
['游戏距离为用户标尺下的近似量。镜头缩放、透视和不同单位血条高度会造成误差；血条中心距离不等于游戏碰撞边缘距离。','Game distances are estimates under your calibration. Zoom, perspective and bar-height offsets introduce error; bar-center distance is not collision-edge distance.'],
['高级：英雄有效参数 JSON / 旧版数据接口','Advanced: effective hero parameters JSON / legacy interface'],
['可运行 fetch-data 查询官方基础数据，再粘贴到此处。必须核验实际攻速、射程、移速、技能等级/消耗/CD、被动与符文状态；只有基础数据不足以评分。','fetch-data downloads official static data. Verify effective attack speed, range, movement speed, skill ranks/costs/cooldowns, passive and rune states. Static data alone is insufficient for scoring.'],
['每方需有 champion、patch、runes、items、effective_state 和 verified_effective_state。后者仅在人工核验后设为 true。','Each side needs champion, patch, runes, items, effective_state and verified_effective_state. Set the last field to true only after verification.'],
['一般对线策略参考（可选）','General matchup strategy (optional)'],['纯文字策略、适用条件、来源链接、版本和访问日期','Strategy prose, applicable conditions, source links, patch and access date'],
['可选：从当前时刻进行短时事件与博弈推演','Optional: short-window event and game analysis'],['启用此项（默认关闭，不影响采样、距离或普通评估）','Enable (off by default; sampling, distances and regular assessment remain available)'],
['先选择介入帧，再生成任务。英雄/小兵机制、有效参数、攻击相位、地面坐标和候选动作需核验；升级、未知转火、仇恨或未实现效果会截断共同有效窗口。','Choose an entry frame and draft a task. Verify rules, effective stats, phases, ground coordinates and candidates. Level-ups, unknown retargeting/aggro or unsupported effects truncate the shared valid window.'],
['金币、经验、血蓝和冷却成本分别结算；未死小兵不视为永久损失。不自动给出胜负或玩家分数。','Report gold, XP, health, mana and cooldown costs separately. Living minions are not permanent losses. No automatic win/loss or player grade is assigned.'],
['非指向技能、被动、符文的观察概率与频率','Observed skillshot, passive and rune probabilities/frequencies'],
['每次技能释放或满足条件的触发机会只记一行，不能把多张截图当作多次机会。已知触发规则优先使用确定计数器；未知结果留空。技能命中、被动触发和符文触发分别使用不同 mechanism_id，并按距离、移动、等级等条件分组。','Record one row per cast or eligible proc opportunity, not per screenshot. Use deterministic counters for known rules; leave unknown outcomes blank. Separate skillshot/passive/rune mechanism IDs and group by distance, movement and level.'],
['下载 UTF-8 BOM 观察表模板','Download UTF-8 BOM observation CSV'],['下载通用机制 JSON 模板','Download generic mechanism JSON'],['将统计模型写入任务（仍须核验适用条件）','Copy estimated models into task (verify applicability)'],['以当前帧生成任务','Draft task at current frame'],
['仅事件分支比较（无需下载）','Event branch comparison (no download)'],['有限零和相对收益（SciPy）','Bounded zero-sum relative payoff (SciPy)'],['双方独立收益（Nashpy）','Independent player payoffs (Nashpy)'],
['生成草稿后，人工或 AI 填写并核验。没有内置任何英雄的参数。','Complete and verify the draft manually or with AI. No champion combat rules are assumed.'],['运行已核验任务','Run verified task'],['机制范围与任务格式','Supported mechanics and task format'],
['已安装','Installed'],['未安装，可选下载','Not installed; optional download'],['可选安装命令（自行在本机终端运行，不自动下载）：','Optional install command (run in your terminal; no automatic installation):'],
['血条中心：未知','Health-bar center: unknown'],['血条中心','Health-bar center'],['与敌方英雄距离：待标注双方中心','Enemy hero distance: annotate both centers'],['与敌方英雄距离：','Enemy hero distance: '],['视频','Video'],
['动作已记录，尚需保存。','Action recorded; save to persist.'],['标尺格式：189=350','Calibration format: 189=350'],['事件表 CSV','Events CSV'],['距离表 CSV','Distances CSV'],['独立评估包 ZIP','Standalone assessment ZIP'],
['不是有效标注 JSON','Invalid annotation JSON'],['已载入标注。保存时将执行结构校验。','Annotations loaded. Structure will be validated on save.'],['先导入观察 CSV','Import observation CSV first'],
['可选推演未启用；其他计算不受影响。','Optional planning is disabled; other calculations remain available.'],['任务介入时刻：视频','Task entry: video'],['草稿未核验，必须补齐参数才能运行。','Unverified draft: complete the parameters before running.'],['有效窗口','Effective window'],['结果已保存','Results saved'],['下载完整推演结果 JSON','Download full result JSON'],
['已写入观察统计。context_verified 保持 false，需核验距离、移动、机制条件及反事实适用性；触发概率不会替代确定规则。','Estimates copied. context_verified remains false; verify distance, movement, eligibility and counterfactual applicability. Proc probabilities do not replace deterministic rules.'],
['波次必须是非负整数；不确定时使用 0 并在备注中说明','Wave must be a nonnegative integer; use 0 with a note if unknown'],['ID 必须唯一；阵亡后也不复用','IDs must be unique, including dead units'],['已加入','Added'],['请在距离对象中显式选取；未知兵种可先用 minion。','Select this unit explicitly in the distance roster; use minion if its type is unknown.']
]);
const uiOriginal=new WeakMap();
window.translateText=function(value){if(window.uiLang!=='en')return value;let text=value;for(let [zh,en] of [...uiTranslations].sort((a,b)=>b[0].length-a[0].length))text=text.split(zh).join(en);return text};
function localizeUI(root=document.body){
 const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);let node;
 while((node=walker.nextNode())){
  if(node.parentElement?.closest('script,style,textarea,pre,[data-user-content]'))continue;
  let previous=uiOriginal.get(node);if(!previous||node.nodeValue!==previous.rendered)previous={original:node.nodeValue};
  let rendered=window.translateText(previous.original);uiOriginal.set(node,{original:previous.original,rendered});if(node.nodeValue!==rendered)node.nodeValue=rendered;
 }
 for(let input of root.querySelectorAll('input[placeholder],textarea[placeholder]')){input.dataset.originalPlaceholder??=input.placeholder;input.placeholder=window.translateText(input.dataset.originalPlaceholder)}
 document.documentElement.lang=window.uiLang==='en'?'en':'zh-CN';
 document.title=window.translateText('LOL 短时补兵决策评估工作台');
}
window.localizeUI=localizeUI;
document.getElementById('uiLanguage').value=window.uiLang;
document.getElementById('uiLanguage').onchange=e=>{window.uiLang=e.target.value;localStorage.setItem('lol-workbench-language',window.uiLang);localizeUI();window.dispatchEvent(new Event('languagechange'))};
localizeUI();
let localeQueued=false;
new MutationObserver(()=>{if(localeQueued)return;localeQueued=true;queueMicrotask(()=>{localeQueued=false;localizeUI()})}).observe(document.body,{subtree:true,childList:true,characterData:true});
