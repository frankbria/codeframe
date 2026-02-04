'use client';

import {
  Time01Icon,
  CheckmarkCircle01Icon,
  PlayIcon,
  Alert02Icon,
  Folder01Icon,
} from '@hugeicons/react';
import { formatDistanceToNow } from 'date-fns';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { ActivityItem, ActivityType } from '@/types';

interface RecentActivityFeedProps {
  activities: ActivityItem[];
}

const MAX_ITEMS = 5;

const activityIcons: Record<ActivityType, React.ElementType> = {
  task_completed: CheckmarkCircle01Icon,
  run_started: PlayIcon,
  blocker_raised: Alert02Icon,
  workspace_initialized: Folder01Icon,
  prd_added: Folder01Icon,
};

const activityColors: Record<ActivityType, string> = {
  task_completed: 'text-green-600',
  run_started: 'text-blue-600',
  blocker_raised: 'text-red-600',
  workspace_initialized: 'text-gray-600',
  prd_added: 'text-purple-600',
};

export function RecentActivityFeed({ activities }: RecentActivityFeedProps) {
  const displayedActivities = activities.slice(0, MAX_ITEMS);

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-4">
        <CardTitle className="flex items-center gap-2 text-base font-semibold">
          <Time01Icon className="h-5 w-5" />
          Recent Activity
        </CardTitle>
      </CardHeader>
      <CardContent>
        {displayedActivities.length === 0 ? (
          <p className="text-sm text-muted-foreground">No recent activity</p>
        ) : (
          <div className="space-y-4">
            {displayedActivities.map((activity, index) => {
              const Icon = activityIcons[activity.type];
              const colorClass = activityColors[activity.type];

              return (
                <div key={activity.id} className="flex gap-3">
                  {/* Timeline connector */}
                  <div className="flex flex-col items-center">
                    <div className={`rounded-full p-1.5 ${colorClass}`}>
                      <Icon className="h-4 w-4" />
                    </div>
                    {index < displayedActivities.length - 1 && (
                      <div className="mt-1 h-full w-px bg-border" />
                    )}
                  </div>

                  {/* Activity content */}
                  <div className="flex-1 pb-4">
                    <p className="text-sm">{activity.description}</p>
                    <p
                      data-testid="activity-timestamp"
                      className="mt-1 text-xs text-muted-foreground"
                    >
                      {formatDistanceToNow(new Date(activity.timestamp), {
                        addSuffix: true,
                      })}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
