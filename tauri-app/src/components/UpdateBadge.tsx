import React from 'react';
import { Badge } from '@/components/ui/badge';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { useUpdater } from '@/hooks/useUpdater';

interface UpdateBadgeProps {
  className?: string;
}

export const UpdateBadge: React.FC<UpdateBadgeProps> = ({ className = '' }) => {
  const { updateAvailable, updateVersion } = useUpdater();

  if (!updateAvailable) {
    return null;
  }

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <div className={`relative ${className}`}>
          <Badge 
            variant="destructive" 
            className="h-2 w-2 p-0 absolute -top-1 -right-1 rounded-full animate-pulse border-2 border-background red-600"
          >
            <span className="sr-only">New version available</span>
          </Badge>
        </div>
      </TooltipTrigger>
      <TooltipContent>
        <p>New version {updateVersion} available</p>
      </TooltipContent>
    </Tooltip>
  );
};
