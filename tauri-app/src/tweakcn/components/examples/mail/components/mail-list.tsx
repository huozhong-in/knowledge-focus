import { ComponentProps } from "react";
import { formatDistanceToNow } from "date-fns";

import { cn } from "@/tweakcn/lib/utils";
import { Badge } from "@/tweakcn/components/ui/badge";
import { ScrollArea } from "@/tweakcn/components/ui/scroll-area";
import { Mail } from "@/tweakcn/components/examples/mail/data";
import { useMail } from "@/tweakcn/components/examples/mail/use-mail";
import { useFullscreen } from "@/tweakcn/hooks/use-fullscreen";
interface MailListProps {
  items: Mail[];
}

export function MailList({ items }: MailListProps) {
  const [mail, setMail] = useMail();
  const { isFullscreen } = useFullscreen();

  return (
    <ScrollArea className={cn("h-screen", isFullscreen && "h-[75%]")}>
      <div className="flex flex-col gap-2 p-4 pt-0">
        {items.map((item) => (
          <button
            key={item.id}
            className={cn(
              "hover:bg-accent hover:text-accent-foreground flex flex-col items-start gap-2 rounded-lg border p-3 text-left text-sm transition-all",
              mail.selected === item.id && "bg-muted"
            )}
            onClick={() =>
              setMail({
                ...mail,
                selected: item.id,
              })
            }
          >
            <div className="flex w-full flex-col gap-1">
              <div className="flex items-center">
                <div className="flex items-center gap-2">
                  <div className="font-semibold">{item.name}</div>
                  {!item.read && <span className="flex h-2 w-2 rounded-full bg-blue-600" />}
                </div>
                <div
                  className={cn(
                    "ml-auto text-xs",
                    mail.selected === item.id ? "text-foreground" : "text-muted-foreground"
                  )}
                >
                  {formatDistanceToNow(new Date(item.date), {
                    addSuffix: true,
                  })}
                </div>
              </div>
              <div className="text-xs font-medium">{item.subject}</div>
            </div>
            <div className="text-muted-foreground line-clamp-2 text-xs">
              {item.text.substring(0, 300)}
            </div>
            {item.labels.length ? (
              <div className="flex items-center gap-2">
                {item.labels.map((label) => (
                  <Badge key={label} variant={getBadgeVariantFromLabel(label)}>
                    {label}
                  </Badge>
                ))}
              </div>
            ) : null}
          </button>
        ))}
      </div>
    </ScrollArea>
  );
}

function getBadgeVariantFromLabel(label: string): ComponentProps<typeof Badge>["variant"] {
  if (["work"].includes(label.toLowerCase())) {
    return "default";
  }

  if (["personal"].includes(label.toLowerCase())) {
    return "outline";
  }

  return "secondary";
}
