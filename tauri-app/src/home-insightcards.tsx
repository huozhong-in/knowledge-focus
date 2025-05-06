import { toast } from "sonner";
import { Button } from "@/components/ui/button";

function HomeInsightCards() {  
  
    const handleToast = () => {
        toast.success("Insight card loaded successfully!");
    };

    return (
      <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
        <div className="grid auto-rows-min gap-4 md:grid-cols-3">
          <div className="aspect-video rounded-xl bg-muted/50">
          <Button
            onClick={() => {
              handleToast();
            }}
          >Show Toast</Button>
          </div>
          <div className="aspect-video rounded-xl bg-muted/50" />
          <div className="aspect-video rounded-xl bg-muted/50" />
        </div>
        <div className="min-h-[100vh] flex-1 rounded-xl bg-muted/50 md:min-h-min" />
      </div>
    );
  }
  
  export default HomeInsightCards;