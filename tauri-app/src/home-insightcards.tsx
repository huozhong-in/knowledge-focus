import { Button } from "@/components/ui/button";
import React from "react";
import {
  Drawer,
  DrawerClose,
  DrawerContent,
  DrawerDescription,
  DrawerFooter,
  DrawerHeader,
  DrawerTitle,
  DrawerTrigger,
} from "@/components/ui/drawer"


interface InsightCardData {
  id: string;
  title: string;
  insightLevel: 1 | 2 | 3; // 1: low, 2: medium, 3: high
}

const mockInsightCards: InsightCardData[] = [
  { id: "1", title: "“新连接发现！” - 您的项目 Alpha 与 Beta 之间似乎产生了新的关联。", insightLevel: 3 },
  { id: "2", title: "“沉睡文件苏醒！” - 文件 report.docx 在沉寂 3个月 后，今天被频繁访问。", insightLevel: 2 },
  { id: "3", title: "“协作热点形成！” - 张三 和 李四 最近在 /docs 目录上的协作异常活跃。", insightLevel: 3 },
  { id: "4", title: "“知识孤岛预警！” - old_research.pdf 似乎很久没有被其他文件引用或更新了。", insightLevel: 1 },
  { id: "5", title: "“版本迭代加速！” - main.py 在过去24小时内经历了 5 次重要修改。", insightLevel: 2 },
  { id: "6", title: "“潜力新星出现！” - 新创建的 proposal_v3.docx 正在迅速积累关注。", insightLevel: 3 },
  { id: "7", title: "“命名一致性提示！” - 检测到 /images 下的文件命名风格略有不同。", insightLevel: 1 },
  { id: "8", title: "“磁盘空间黑洞？” - /backup/archive.zip 的体积增长异常迅速。", insightLevel: 2 },
  { id: "9", title: "“依赖关系变更！” - componentA.tsx 对 utils.ts 的依赖关系似乎发生了变化。", insightLevel: 2 },
  { id: "10", title: "“权限变更提醒！” - shared_folder 的访问权限刚刚被修改。", insightLevel: 1 },
  { id: "11", title: "“关键词‘AI伦理’热度飙升！” - 在您的最新文档中，这个词汇的出现频率显著增加。", insightLevel: 3 },
  { id: "12", title: "“情感倾向变化！” - customer_feedback.txt 中的文本内容似乎从“中性”转变为“积极”。", insightLevel: 2 },
  { id: "13", title: "“代码复杂度攀升！” - api_service.java 的复杂度指标有所上升。", insightLevel: 2 },
  { id: "14", title: "“文档过期预警！” - product_manual_v1.pdf 的内容可能已过时，上次更新还是在 2023年。", insightLevel: 1 },
  { id: "15", title: "“重复模式涌现！” - 在 script1.sh 和 script2.sh 中发现了高度相似的内容片段。", insightLevel: 2 },
  { id: "16", title: "“创新模式初探！” - new_design_concept.fig 中出现了一种全新的交互模式。", insightLevel: 3 },
  { id: "17", title: "“被遗忘的智慧！” - 您的旧文件 notes_2020.md 中似乎包含了与当前项目相关的重要信息。", insightLevel: 2 },
  { id: "18", title: "“跨领域知识交汇！” - marketing_strategy.pptx 和 sales_data.xlsx 虽然主题不同，但似乎在增长点上有所交集。", insightLevel: 3 },
  { id: "19", title: "“决策依据强化！” - 新增的 user_survey_results.csv 为您的产品路线图提供了更充分的数据支持。", insightLevel: 3 },
  { id: "20", title: "“风险信号闪烁！” - legal_contract.docx 中提及的“赔偿条款”频率增加。", insightLevel: 1 },
  { id: "21", title: "“时间胶囊开启！” - 您刚刚打开了一个 1年 未曾触碰的 project_archive_2022.zip。", insightLevel: 2 },
  { id: "22", title: "“灵感火花碰撞！” - idea_sketch.png 的修改似乎与 brainstorming_notes.txt 的创建在时间上高度吻合。", insightLevel: 3 },
  { id: "23", title: "“代码诗人上线！” - /utils/helpers.js 中的注释风格突然变得很有诗意！", insightLevel: 1 },
  { id: "24", title: "“神秘文件现身！” - 一个名为 aXyZ_temp.dat 的文件出现在了您的工作区。", insightLevel: 2 },
  { id: "25", title: "“专注力爆表！” - 您在 上午10点-12点 内对 /feature-x 目录的投入异乎寻常地高。", insightLevel: 3 },
  { id: "26", title: "“夜猫子模式启动！” - 系统检测到您在凌晨2点对 server_config.json 进行了重要更新。", insightLevel: 2 },
  { id: "27", title: "“隐藏的关联！” - 文件 image_001.jpg 和 photo_archive_001.png 的创建者都喜欢在文件名中使用下划线。", insightLevel: 1 },
  { id: "28", title: "“数字“3”的魔力？” - 今天有3个文件被命名包含数字“3”。", insightLevel: 1 },
  { id: "29", title: "“色彩偏好分析！” - 您最近创建的 presentation_theme.pptx 似乎偏爱蓝色系。", insightLevel: 2 },
  { id: "30", title: "“年度回顾预热！” - main_project_plan.mpp 是您今年编辑次数最多的文件之一。", insightLevel: 3 },
];



function HomeInsightCards() {
    // Removed const [open, setOpen] = React.useState(false) as it's now managed by each InsightCardDrawer

    // InsightCardDrawer component is defined inside HomeInsightCards, managing its own state.
    function InsightCardDrawer({ card }: { card: InsightCardData }) {
    const [isOpen, setIsOpen] = React.useState(false);

    // Mock data for related files - replace with actual data fetching logic
    const relatedFiles = [
      { name: "File_A.pdf", path: "/documents/project_alpha/File_A.pdf" },
      { name: "Note_XYZ.txt", path: "/notes/personal/Note_XYZ.txt" },
      { name: "Change_123.diff", path: "/code/feature/Change_123.diff" },
    ];

    return (
      <Drawer open={isOpen} onOpenChange={setIsOpen} direction="right">
        <DrawerTrigger asChild>
          <Button variant="ghost" size="sm" className="self-start mt-2 text-white hover:bg-white/20">
            Explore
          </Button>
        </DrawerTrigger>
        <DrawerContent className="w-[350px] sm:w-[450px] p-4"> {/* Adjust width as needed */}
          <DrawerHeader className="p-0 mb-4">
            <DrawerTitle className="mb-1">Insight: {card.title}</DrawerTitle>
            <DrawerDescription>
              Related files for this insight:
            </DrawerDescription>
          </DrawerHeader>
          
          <div className="flex-grow overflow-auto mb-4">
            {relatedFiles.length > 0 ? (
              <ul className="space-y-2">
                {relatedFiles.map((file, index) => (
                  <li key={index} className="text-sm p-2 rounded-md bg-muted/50">
                    <p className="font-semibold">{file.name}</p>
                    <p className="text-xs text-muted-foreground">{file.path}</p>
                  </li>
                ))}
              </ul>
            ) : (
              <p>No related files found for this insight.</p>
            )}
          </div>

          <DrawerFooter className="p-0">
            <DrawerClose asChild>
              <Button variant="outline">Close</Button>
            </DrawerClose>
          </DrawerFooter>
        </DrawerContent>
      </Drawer>
    );
  }
  
    const getCardStyle = (level: 1 | 2 | 3) => {
      switch (level) {
        case 1: return "bg-[#e6c3a5] hover:bg-[#e6c3a5]/90"; // Lighter
        case 2: return "bg-[#d29b71] hover:bg-[#d29b71]/90"; // Base
        case 3: return "bg-[#b8855f] hover:bg-[#b8855f]/90"; // Darker
        default: return "bg-muted/50 hover:bg-muted/40";
      }
    };

    return (
      <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
        <div className="grid auto-rows-min gap-4 md:grid-cols-3">
          {mockInsightCards.map((card) => (
            <div 
              key={card.id} 
              className={`aspect-video rounded-xl p-4 flex flex-col justify-between text-white transition-colors ${getCardStyle(card.insightLevel)}`}
            >
              <p className="text-sm font-medium">{card.title}</p>
              {/* Render InsightCardDrawer directly; it contains its own trigger button */}
              <InsightCardDrawer card={card} />
            </div>
          ))}
        </div>
      </div>
    );
  }
  
  export default HomeInsightCards;