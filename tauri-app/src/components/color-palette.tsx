import { whiskeyColors } from "@/theme/whiskey-colors";

/**
 * 颜色预览组件
 * 用于展示自定义颜色的各个色阶
 */
export function ColorPalette() {
  // 所有色阶
  const colorShades = Object.keys(whiskeyColors).map(Number).sort((a, b) => a - b) as (keyof typeof whiskeyColors)[];

  return (
    <div className="p-6 space-y-6">
      <h2 className="text-2xl font-bold">威士忌颜色系统</h2>
      
      <div className="space-y-2">
        <h3 className="text-xl font-semibold">基础色阶</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="space-y-2">
            {colorShades.map(shade => (
              <div key={shade} className="flex items-center gap-3">
                <div 
                  className={`w-12 h-12 rounded-md`}
                  style={{ backgroundColor: whiskeyColors[shade] }}
                />
                <div>
                  <div className="font-mono text-sm">{whiskeyColors[shade as keyof typeof whiskeyColors]}</div>
                  <div className="text-xs text-muted-foreground">whiskey-{shade}</div>
                </div>
              </div>
            ))}
          </div>
          
          <div className="space-y-4">
            <div>
              <h4 className="text-sm font-medium mb-2">Tailwind 类示例</h4>
              <div className="flex flex-wrap gap-2">
                {colorShades.map(shade => {
                  // Find the reverse color shade (e.g., if 50 is lightest and 950 is darkest)
                  const maxShade = Math.max(...colorShades);
                  const minShade = Math.min(...colorShades);
                  const reverseShade = maxShade - (shade - minShade);
                  
                  return (
                    <div 
                      key={shade}
                      className={`bg-whiskey-${shade} text-whiskey-${reverseShade} text-xs px-3 py-1 rounded-full`}
                    >
                      bg-whiskey-{shade}
                    </div>
                  );
                })}
              </div>
            </div>
            
            <div>
              <h4 className="text-sm font-medium mb-2">文本颜色示例</h4>
              <div className="flex flex-wrap gap-2">
                {colorShades.map(shade => (
                  <div 
                    key={shade}
                    className={`text-whiskey-${shade} text-sm font-medium px-2`}
                  >
                    文本 {shade}
                  </div>
                ))}
              </div>
            </div>
            
            <div>
              <h4 className="text-sm font-medium mb-2">边框颜色示例</h4>
              <div className="flex flex-wrap gap-2">
                {['200', '300', '400', '500'].map(shade => (
                  <div 
                    key={shade}
                    className={`border-2 border-whiskey-${shade} px-3 py-1 rounded-md text-xs`}
                  >
                    border-whiskey-{shade}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
      
      <div className="space-y-2">
        <h3 className="text-xl font-semibold">组件示例</h3>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="p-4 bg-whiskey-50 border border-whiskey-200 rounded-lg">
            bg-whiskey-50 + border-whiskey-200
          </div>
          <div className="p-4 bg-whiskey-100 text-whiskey-900 rounded-lg">
            bg-whiskey-100 + text-whiskey-900
          </div>
          <div className="p-4 bg-whiskey-200 text-whiskey-800 font-medium rounded-lg">
            bg-whiskey-200 + text-whiskey-800
          </div>
          <div className="p-4 bg-whiskey-300 text-whiskey-950 font-medium rounded-lg">
            bg-whiskey-300 + text-whiskey-950
          </div>
          <div className="p-4 bg-whiskey-400 text-white font-medium rounded-lg">
            bg-whiskey-400 + text-white
          </div>
          <div className="p-4 bg-whiskey-500 text-white font-medium rounded-lg">
            bg-whiskey-500 + text-white
          </div>
        </div>
      </div>
    </div>
  );
}
