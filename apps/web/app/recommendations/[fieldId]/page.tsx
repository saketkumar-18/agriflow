import { Protected } from "@/components/protected";
import { RecommendationPage } from "../pages";

export default async function RecommendationRoute({ params }: { params: Promise<{ fieldId: string }> }) {
  const { fieldId } = await params;
  return (
    <Protected>
      <RecommendationPage fieldId={fieldId} />
    </Protected>
  );
}
