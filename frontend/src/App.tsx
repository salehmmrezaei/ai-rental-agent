import { Component, useEffect } from "react";
import type { ReactNode } from "react";
import { Link, Route, Routes, useLocation, useParams } from "react-router-dom";
import { AuthGate, DashboardRedirect } from "./auth/AuthGate";
import { PublicLayout } from "./layouts/PublicLayout";
import { DashboardLayout } from "./layouts/DashboardLayout";
import { Home } from "./pages/Home";
import { SearchPage } from "./pages/Search";
import { ListingDetailPage } from "./pages/ListingDetail";
import { AuthPage } from "./pages/Auth";
import { OverviewPage } from "./pages/Overview";
import { SavedPage } from "./pages/Saved";
import { ApplicationsPage } from "./pages/Applications";
import { ContractsPage } from "./pages/Contracts";
import { VisitsPage } from "./pages/Visits";
import { MessagesPage } from "./pages/Messages";
import { ProfilePage } from "./pages/Profile";
import { PropertiesPage } from "./pages/Properties";
import { PropertyEditorPage } from "./pages/PropertyEditor";
import { PropertyManagePage } from "./pages/PropertyManage";
import { OccupancyPage } from "./pages/Occupancy";
import { ListingApprovalsPage } from "./pages/ListingApprovals";
import { UsersPage } from "./pages/Users";
import { AssistantPage } from "./pages/Assistant";
import { Button, Empty } from "./components/ui";
import { FloatingCompanion } from "./components/FloatingCompanion";
export class ErrorBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? (
      <div className="container">
        <Empty
          title="Something went wrong"
          action={
            <Button onClick={() => window.location.reload()}>
              Reload page
            </Button>
          }
        >
          Please reload to try again.
        </Empty>
      </div>
    ) : (
      this.props.children
    );
  }
}
function ListingDetailRoute() {
  const { id } = useParams();
  return <ListingDetailPage key={id} />;
}
function PropertyManageRoute() {
  const { id } = useParams();
  return <PropertyManagePage key={id} />;
}
function RouteEffects() {
  const { pathname } = useLocation();
  useEffect(() => {
    window.scrollTo(0, 0);
    document.title = `${pathname === "/" ? "Find your home in Italy" : pathname.startsWith("/listings") ? "Find a home" : pathname === "/login" ? "Sign in" : pathname === "/register" ? "Create an account" : "Your rental workspace"} · Casa`;
  }, [pathname]);
  return null;
}
export function App() {
  return (
    <ErrorBoundary>
      <RouteEffects />
      <Routes>
        <Route element={<PublicLayout />}>
          <Route index element={<Home />} />
          <Route path="listings" element={<SearchPage />} />
          <Route path="listings/:id" element={<ListingDetailRoute />} />
          <Route path="login" element={<AuthPage />} />
          <Route path="register" element={<AuthPage register />} />
        </Route>
        <Route element={<AuthGate roles={["tenant", "landlord", "admin"]} />}>
          <Route path="dashboard" element={<DashboardRedirect />} />
        </Route>
        <Route element={<AuthGate roles={["tenant"]} />}>
          <Route path="tenant" element={<DashboardLayout />}>
            <Route index element={<OverviewPage />} />
            <Route path="assistant" element={<AssistantPage />} />
            <Route path="saved" element={<SavedPage />} />
            <Route path="applications" element={<ApplicationsPage />} />
            <Route path="contracts" element={<ContractsPage />} />
            <Route path="visits" element={<VisitsPage />} />
            <Route path="messages" element={<MessagesPage />} />
            <Route path="profile" element={<ProfilePage />} />
          </Route>
        </Route>
        <Route element={<AuthGate roles={["landlord"]} />}>
          <Route path="landlord" element={<DashboardLayout />}>
            <Route index element={<OverviewPage />} />
            <Route path="properties" element={<PropertiesPage />} />
            <Route path="properties/new" element={<PropertyEditorPage />} />
            <Route path="properties/:id" element={<PropertyManageRoute />} />
            <Route
              path="properties/:id/edit"
              element={<PropertyEditorPage />}
            />
            <Route path="occupancy" element={<OccupancyPage />} />
            <Route path="contracts" element={<ContractsPage />} />
            <Route path="profile" element={<ProfilePage />} />
          </Route>
        </Route>
        <Route element={<AuthGate roles={["admin"]} />}>
          <Route path="admin" element={<DashboardLayout />}>
            <Route index element={<OverviewPage />} />
            <Route path="assistant" element={<AssistantPage />} />
            <Route path="users" element={<UsersPage />} />
            <Route path="properties" element={<PropertiesPage />} />
            <Route path="properties/new" element={<PropertyEditorPage />} />
            <Route path="properties/:id" element={<PropertyManageRoute />} />
            <Route
              path="properties/:id/edit"
              element={<PropertyEditorPage />}
            />
            <Route path="listings" element={<ListingApprovalsPage />} />
            <Route path="applications" element={<ApplicationsPage />} />
            <Route path="contracts" element={<ContractsPage />} />
            <Route path="visits" element={<VisitsPage />} />
            <Route path="messages" element={<MessagesPage />} />
            <Route path="occupancy" element={<OccupancyPage />} />
            <Route path="profile" element={<ProfilePage />} />
          </Route>
        </Route>
        <Route element={<PublicLayout />}>
          <Route
            path="*"
            element={
              <div className="container">
                <Empty
                  title="This page has moved on"
                  action={
                    <Link className="btn btn-primary" to="/">
                      Back to Casa
                    </Link>
                  }
                >
                  Let’s find somewhere else to go.
                </Empty>
              </div>
            }
          />
        </Route>
      </Routes>
      <FloatingCompanion />
    </ErrorBoundary>
  );
}
