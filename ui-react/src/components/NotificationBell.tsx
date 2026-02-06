import { useState } from "react";
import { Bell } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

export function NotificationBell() {
  const [showDropdown, setShowDropdown] = useState(false);

  // Check for platform updates (every 15 minutes - reads from cached database)
  const { data: platformUpdates } = useQuery({
    queryKey: ["platform-updates"],
    queryFn: async () => {
      const response = await fetch("/api/updates/check");
      if (!response.ok) return null;
      return response.json();
    },
    refetchInterval: 900000, // 15 minutes
  });

  // Check for driver updates (every 15 minutes)
  const { data: driverUpdates } = useQuery({
    queryKey: ["driver-updates"],
    queryFn: async () => {
      const response = await fetch("/api/drivers/check-updates");
      if (!response.ok) return null;
      return response.json();
    },
    refetchInterval: 900000, // 15 minutes
  });

  // Calculate total updates
  const platformUpdateAvailable = platformUpdates?.update_available ? 1 : 0;
  const driverUpdatesAvailable = driverUpdates?.filter((d: any) => d.update_available)?.length || 0;
  const totalUpdates = platformUpdateAvailable + driverUpdatesAvailable;

  if (totalUpdates === 0) return null;

  return (
    <div className="relative">
      <button
        onClick={() => setShowDropdown(!showDropdown)}
        className="relative p-2 rounded-lg hover:bg-accent transition-colors"
        aria-label="Notifications"
      >
        <Bell className="w-5 h-5" />
        {totalUpdates > 0 && (
          <span className="absolute -top-1 -right-1 flex h-5 w-5 items-center justify-center rounded-full bg-red-500 text-[10px] font-bold text-white">
            {totalUpdates > 9 ? "9+" : totalUpdates}
          </span>
        )}
      </button>

      {/* Dropdown */}
      {showDropdown && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 z-40"
            onClick={() => setShowDropdown(false)}
          />

          {/* Dropdown content */}
          <div className="absolute right-0 top-12 z-50 w-80 rounded-lg border bg-background shadow-lg">
            <div className="border-b p-4">
              <h3 className="font-semibold">Updates Available</h3>
              <p className="text-sm text-muted-foreground">
                {totalUpdates} update{totalUpdates !== 1 ? "s" : ""} available
              </p>
            </div>

            <div className="max-h-96 overflow-y-auto">
              {/* Platform Update */}
              {platformUpdates?.update_available && (
                <Link
                  to="/settings/platform"
                  className="block border-b p-4 hover:bg-accent transition-colors"
                  onClick={() => setShowDropdown(false)}
                >
                  <div className="flex items-start gap-3">
                    <div className="rounded-full bg-purple-500/10 p-2">
                      <Bell className="w-4 h-4 text-purple-500" />
                    </div>
                    <div className="flex-1">
                      <h4 className="font-medium">Platform Update</h4>
                      <p className="text-sm text-muted-foreground">
                        {platformUpdates.current_tag} → {platformUpdates.latest_tag}
                      </p>
                      {platformUpdates.commits_behind > 0 && (
                        <p className="text-xs text-muted-foreground mt-1">
                          {platformUpdates.commits_behind} commit{platformUpdates.commits_behind !== 1 ? "s" : ""} behind
                        </p>
                      )}
                    </div>
                  </div>
                </Link>
              )}

              {/* Driver Updates */}
              {driverUpdates?.filter((d: any) => d.update_available).map((driver: any) => (
                <Link
                  key={driver.name}
                  to="/settings/drivers"
                  className="block border-b p-4 hover:bg-accent transition-colors last:border-b-0"
                  onClick={() => setShowDropdown(false)}
                >
                  <div className="flex items-start gap-3">
                    <div className="rounded-full bg-blue-500/10 p-2">
                      <Bell className="w-4 h-4 text-blue-500" />
                    </div>
                    <div className="flex-1">
                      <h4 className="font-medium">{driver.name}</h4>
                      <p className="text-sm text-muted-foreground">
                        {driver.current_version} → {driver.latest_version}
                      </p>
                    </div>
                  </div>
                </Link>
              ))}
            </div>

            <div className="border-t p-3 text-center">
              <Link
                to="/settings/platform"
                className="text-sm text-muted-foreground hover:text-foreground transition-colors"
                onClick={() => setShowDropdown(false)}
              >
                View all updates →
              </Link>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
