# Movie Recommender

Sustav za preporuku filmova.
Projekt je dio kolegija Infrastruktura podataka velikog obujma (IPVO) na Fakultetu Informatike i Digitalnih tehnologija.

Faza 1: Backend servis + baza podataka + skalabilnost.
Baza se pokreće s docker compose up --build i onda se testira na http://localhost
Frontend za prvu fazu napravio kolega. Login i register funkcionalnosti.

Faza 2: Batch processor i dataset za future ML training (MinIO). 
Sustav uzima ratings i movie_id svih filmova kako bi sakupio podatke za sustav preporuke filmova.
S pokretanjem dockera pokreće se i batch processing koji se obrađuje jednom, zatim se pokreće MinIO na http://localhost:9001 (minioadmin/minioadmin) gdje se mogu skinuti prikupljeni podatci (csv datoteka) i reccomendations (json).

Faza 3: Predmemorija (Redis) + nadzor performansi (Prometheus + Grafana). 
Dodaje se Redis za cache često korištenih podataka (popularni filmovi). 
Prometheus i Grafana prate performanse API-ja, baze i cachea. 
Svi servisi Dockerizirani za lakše skaliranje. Pokreće se s docker compose up --build.
Cache test: localhost/ 2x → vidi "Cache MISS→HIT" u backend logovima. 
Metrics: localhost:9090, Grafana: localhost:3000 (admin/admin).
