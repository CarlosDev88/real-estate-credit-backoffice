import { redirect } from "next/navigation";

// El login decide el destino (next o la primera entrada permitida del menú).
export default function Home() {
  redirect("/login");
}
