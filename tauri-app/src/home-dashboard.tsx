"use client"
import React from "react"
import { TrendingUp } from "lucide-react"
import { Area, AreaChart, CartesianGrid, XAxis } from "recharts"
import { Label, Pie, PieChart } from "recharts"
import { Bar, BarChart} from "recharts"
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  ChartConfig,
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
} from "@/components/ui/chart"

function HomeInsightCards() {
  interface InsightCardData {
    id: string;
    title: string;
    insightLevel: 1 | 2 | 3; // 1: low, 2: medium, 3: high
    priorityLabel?: string; // 优先级标签
    timestamp?: string; // 时间戳
  }
  const mockInsightCards: InsightCardData[] = [
    { 
      id: "1", 
      title: "“沉睡文件苏醒！” - 文件 report.docx 在沉寂 3个月 后，今天被频繁访问。", 
      insightLevel: 3,
      priorityLabel: "Top 1",
      timestamp: "今天 10:23"
    },
    { 
      id: "2", 
      title: "“磁盘空间黑洞？” - /backup/archive.zip 的体积增长异常迅速。", 
      insightLevel: 2,
      priorityLabel: "Top 2",
      timestamp: "今天 09:15"
    },
    { 
      id: "3", 
      title: "“时间胶囊开启！” - 您刚刚打开了一个 1年 未曾触碰的 project_archive_2022.zip。", 
      insightLevel: 1,
      priorityLabel: "Top 3",
      timestamp: "昨天 18:42"
    },
  ];  
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
            <div className="flex justify-between items-start mb-2">
              {card.priorityLabel && (
                <span className="px-2 py-0.5 rounded-full bg-white/20 text-xs font-semibold">
                  {card.priorityLabel}
                </span>
              )}
              {card.timestamp && (
                <span className="text-xs text-white/70">
                  {card.timestamp}
                </span>
              )}
            </div>
            <p className="text-sm font-medium">{card.title}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
const chartData = [
  { month: "1月", documents: 186, media: 80 },
  { month: "2月", documents: 305, media: 200 },
  { month: "3月", documents: 237, media: 120 },
  { month: "4月", documents: 73, media: 190 },
  { month: "5月", documents: 209, media: 130 },
  { month: "6月", documents: 214, media: 140 },
]

const chartConfig = {
  documents: {
    label: "文档文件",
    color: "var(--chart-1)",
  },
  media: {
    label: "媒体文件",
    color: "var(--chart-2)",
  },
} satisfies ChartConfig
const chartData2 = [
  { fileType: "文档", count: 275, fill: "var(--chart-1)" },
  { fileType: "图片", count: 200, fill: "var(--chart-2)" },
  { fileType: "视频", count: 287, fill: "var(--chart-3)" },
  { fileType: "音频", count: 173, fill: "var(--chart-4)" },
  { fileType: "其他", count: 190, fill: "var(--chart-5)" },
]
const chartConfig2 = {
  count: {
    label: "文件数量",
  },
  文档: {
    label: "文档",
    color: "var(--chart-1)",
  },
  图片: {
    label: "图片",
    color: "var(--chart-2)",
  },
  视频: {
    label: "视频",
    color: "var(--chart-3)",
  },
  音频: {
    label: "音频",
    color: "var(--chart-4)",
  },
  其他: {
    label: "其他",
    color: "var(--chart-5)",
  },
} satisfies ChartConfig
const chartData3 = [
  { month: "1月", created: 186, accessed: 80 },
  { month: "2月", created: 305, accessed: 200 },
  { month: "3月", created: 237, accessed: 120 },
  { month: "4月", created: 73, accessed: 190 },
  { month: "5月", created: 209, accessed: 130 },
  { month: "6月", created: 214, accessed: 140 },
]
const chartConfig3 = {
  created: {
    label: "新建文件",
    color: "var(--chart-1)",
  },
  accessed: {
    label: "访问文件",
    color: "var(--chart-2)",
  },
} satisfies ChartConfig

function StackedAreaChart() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>文件类型趋势</CardTitle>
        <CardDescription>
          最近6个月文档与媒体文件变化趋势
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ChartContainer config={chartConfig}>
          <AreaChart
            accessibilityLayer
            data={chartData}
            margin={{
              left: 12,
              right: 12,
            }}
          >
            <CartesianGrid vertical={false} />
            <XAxis
              dataKey="month"
              tickLine={false}
              axisLine={false}
              tickMargin={8}
              tickFormatter={(value) => value.slice(0, 3)}
            />
            <ChartTooltip
              cursor={false}
              content={<ChartTooltipContent indicator="dot" />}
            />
            <Area
              dataKey="media"
              type="natural"
              fill="var(--chart-2)"
              fillOpacity={0.4}
              stroke="var(--chart-2)"
              stackId="a"
            />
            <Area
              dataKey="documents"
              type="natural"
              fill="var(--chart-1)"
              fillOpacity={0.4}
              stroke="var(--chart-1)"
              stackId="a"
            />
          </AreaChart>
        </ChartContainer>
      </CardContent>
      <CardFooter>
        <div className="flex w-full items-start gap-2 text-sm">
          <div className="grid gap-2">
            <div className="flex items-center gap-2 font-medium leading-none">
              文档文件增长5.2% <TrendingUp className="h-4 w-4" />
            </div>
            <div className="flex items-center gap-2 leading-none text-muted-foreground">
              2025年1月 - 6月统计
            </div>
          </div>
        </div>
      </CardFooter>
    </Card>
  )
}

function PieChartWithText() {
  const totalFiles = React.useMemo(() => {
    return chartData2.reduce((acc, curr) => acc + curr.count, 0)
  }, [])
  return (
    <Card className="flex flex-col">
      <CardHeader className="items-center pb-0">
        <CardTitle>文件类型分布</CardTitle>
        <CardDescription>2025年文件类型统计</CardDescription>
      </CardHeader>
      <CardContent className="flex-1 pb-0">
        <ChartContainer
          config={chartConfig2}
          className="mx-auto aspect-square max-h-[250px]"
        >
          <PieChart>
            <ChartTooltip
              cursor={false}
              content={<ChartTooltipContent hideLabel />}
            />
            <Pie
              data={chartData2}
              dataKey="count"
              nameKey="fileType"
              innerRadius={60}
              strokeWidth={5}
            >
              <Label
                content={({ viewBox }) => {
                  if (viewBox && "cx" in viewBox && "cy" in viewBox) {
                    return (
                      <text
                        x={viewBox.cx}
                        y={viewBox.cy}
                        textAnchor="middle"
                        dominantBaseline="middle"
                      >
                        <tspan
                          x={viewBox.cx}
                          y={viewBox.cy}
                          className="fill-foreground text-3xl font-bold"
                        >
                          {totalFiles.toLocaleString()}
                        </tspan>
                        <tspan
                          x={viewBox.cx}
                          y={(viewBox.cy || 0) + 24}
                          className="fill-muted-foreground"
                        >
                          文件总数
                        </tspan>
                      </text>
                    )
                  }
                }}
              />
            </Pie>
          </PieChart>
        </ChartContainer>
      </CardContent>
      <CardFooter className="flex-col gap-2 text-sm">
        <div className="flex items-center gap-2 font-medium leading-none">
          图片文件增长12.7% <TrendingUp className="h-4 w-4" />
        </div>
        <div className="leading-none text-muted-foreground">
          显示所有被监控文件夹的文件分布
        </div>
      </CardFooter>
    </Card>
  )
}
function BarChartMultiple() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>文件活动情况</CardTitle>
        <CardDescription>2025年新建与访问统计</CardDescription>
      </CardHeader>
      <CardContent>
        <ChartContainer config={chartConfig3}>
          <BarChart accessibilityLayer data={chartData3}>
            <CartesianGrid vertical={false} />
            <XAxis
              dataKey="month"
              tickLine={false}
              tickMargin={10}
              axisLine={false}
              tickFormatter={(value) => value.slice(0, 3)}
            />
            <ChartTooltip
              cursor={false}
              content={<ChartTooltipContent indicator="dashed" />}
            />
            <Bar dataKey="created" fill="var(--chart-1)" radius={4} />
            <Bar dataKey="accessed" fill="var(--chart-2)" radius={4} />
          </BarChart>
        </ChartContainer>
      </CardContent>
      <CardFooter className="flex-col items-start gap-2 text-sm">
        <div className="flex gap-2 font-medium leading-none">
          访问文件量增长9.5% <TrendingUp className="h-4 w-4" />
        </div>
        <div className="leading-none text-muted-foreground">
          展示2025年上半年文件活动情况
        </div>
      </CardFooter>
    </Card>
  )
}
function HomeDashboard() {  
  
    return (
      <div className="flex flex-1 flex-col gap-2 p-4 pt-0">
        <HomeInsightCards />
        <div className="grid auto-rows-min gap-2 md:grid-cols-3">
          <StackedAreaChart />
          <PieChartWithText />
          <BarChartMultiple />
        </div>
      </div>
    );
  }
  
export default HomeDashboard;