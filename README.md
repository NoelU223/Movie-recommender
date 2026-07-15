# Movie Recommender

Sustav za preporuku filmova.
Projekt je dio kolegija Infrastruktura podataka velikog obujma (IPVO) i Analitika podataka velikog obujma (APVO) na Fakultetu Informatike i Digitalnih tehnologija.
Prvih 3 faza su dio kolegija IPVO, a posljednja dio kolegija APVO.

Faza 1: Backend servis + baza podataka + skalabilnost.
Baza se pokreće s docker compose up --build i onda se testira na http://localhost
Frontend napravljen koristeći FastAPI. Login i register funkcionalnosti.

Faza 2: Batch processor i dataset za future ML training (MinIO). 
Sustav uzima ratings i movie_id svih filmova kako bi sakupio podatke za sustav preporuke filmova.
S pokretanjem dockera pokreće se i batch processing koji se obrađuje jednom, zatim se pokreće MinIO na http://localhost:9001 (minioadmin/minioadmin) gdje se mogu skinuti prikupljeni podatci (csv datoteka) i reccomendations (json).

Faza 3: Predmemorija (Redis) + nadzor performansi (Prometheus + Grafana). 
Dodaje se Redis za cache često korištenih podataka (popularni filmovi). 
Prometheus i Grafana prate performanse API-ja, baze i cachea. 
Svi servisi Dockerizirani za lakše skaliranje. Pokreće se s docker compose up --build.
Cache test: localhost/ 2x → vidi "Cache MISS→HIT" u backend logovima. 
Metrics: localhost:9090, Grafana: localhost:3000 (admin/admin).

Faza 4: Analitički sloj + streaming + strojno učenje. Aplikacija se proširuje s prikupljanjem korisničkih događaja u realnom vremenu i AI sustavom za predikciju korisničkih preferencija.
Filmovi se automatski uvoze iz TMDB API-ja (poster, opis, ocjena, popularnost) — više nije potreban ručni unos. Svaki korisnički klik (posjet filmu, ocjenjivanje, dodavanje u listu) bilježi se kao događaj u Apache Kafka topic, a zaseban consumer ih arhivira u MinIO kao CSV datoteke. Dodane su funkcionalnosti Watchlist i Favoriti te korisnička profilna stranica.
ML model treniran je na korisničkim ocjenama (binarna klasifikacija — hoće li korisnik dati ocjenu ≥ 7). Uspoređena su tri klasifikatora: Naive Bayes, Logistic Regression i Random Forest. Najbolji model (Random Forest, F1=0.75, AUC=0.90) integriran je u aplikaciju kroz /predict/{movie_id} endpoint, a predikcija se prikazuje kao AI badge na stranici filma.
Pokretanje: docker compose up --build. Generiranje sintetičkih podataka za demonstraciju: docker compose run --rm data_generator. Treniranje modela: docker compose run --rm ml_trainer. TMDB token postavlja se u .env datoteku (TMDB_TOKEN=...).
Nove tehnologije: Apache Kafka, scikit-learn, TMDB API. MinIO (Faza 2) sada služi i za arhivu događaja, ne samo dataset za trening.

