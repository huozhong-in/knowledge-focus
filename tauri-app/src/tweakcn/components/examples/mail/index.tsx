import { Mail } from "@/tweakcn/components/examples/mail/components/mail";
import { accounts, mails } from "@/tweakcn/components/examples/mail/data";

export default function MailPage() {
  return <Mail accounts={accounts} mails={mails} navCollapsedSize={4} />;
}
