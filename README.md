# 🎮 PS4 Games Database

> Catálogo de jogos de PS4 com busca, filtros, informações e links externos.

## 🌐 Acessar

**[🚀 Abrir a página online](https://ps4-games-database-fix.vercel.app/)**

A versão web continua hospedada na Vercel. O aplicativo Android, porém, foi preparado para não depender dela para a interface ou para os metadados locais.

## 📱 APK Android

**[⬇️ Baixar o APK mais recente](https://github.com/Miguellbr/ps4-games-databaseFIX/releases/latest/download/app-debug.apk)**

Também é possível encontrar todas as versões na página de **[Releases](https://github.com/Miguellbr/ps4-games-databaseFIX/releases)**.

> O APK é gerado automaticamente pelo GitHub Actions e publicado como uma Release. A versão inicial é um APK de teste/debug para instalação direta no Android.

## ✨ Recursos

- 🔎 Pesquisa rápida no catálogo
- 🎮 Catálogo local de jogos
- 🔤 Organização e filtros
- 🖼️ Suporte a capas e metadados
- 🌎 Informações em inglês e português quando disponíveis
- 🔗 Links externos de download
- 📱 Interface adaptada para celular
- 🎮 Suporte a controles/gamepad já presente no projeto
- 📦 Versão Android baseada em Capacitor

## 📴 Arquitetura sem dependência da Vercel

O APK não precisa de um servidor Vercel para executar a aplicação.

A estrutura é:

```
Android APK
   │
   ├── Interface HTML/CSS/JS
   ├── Catálogo local
   ├── metadata.json
   └── Capacitor
          │
          └── Android
```

O arquivo `metadata.json` é o armazenamento local de metadados que o APK pode utilizar diretamente.

A Vercel permanece apenas como hospedagem da **versão web** e como fallback da versão web quando necessário. Ela não é necessária para abrir o aplicativo Android.

### Dados locais

- `ps4_games_expanded.json` — catálogo principal.
- `metadata.json` — banco local de metadados para o APK.
- `index.html` — interface principal.
- `capacitor.config.ts` — configuração do aplicativo Android.

## 🏗️ Como o APK é construído

O projeto usa **Capacitor** para transformar a aplicação web em um aplicativo Android.

O GitHub Actions:

1. instala Node.js;
2. instala Java;
3. instala as dependências do Capacitor;
4. gera o projeto Android;
5. copia a aplicação web para o Android;
6. compila o APK;
7. publica o APK como uma GitHub Release.

Não é necessário manter a pasta `android/` gerada no repositório.

## 🔧 Estrutura principal

```
ps4-games-databaseFIX/
├── index.html
├── ps4_games_expanded.json
├── metadata.json
├── catalog.json
├── manifest.json
├── capacitor.config.ts
├── package.json
├── api/
│   └── ps4-metadata.js
├── .github/
│   └── workflows/
│       └── build-apk.yml
└── README.md
```

## 🚀 Gerar uma nova versão do APK

No GitHub:

**Actions → Build Android APK → Run workflow**

Depois que o processo terminar, uma nova Release será criada automaticamente.

O arquivo poderá ser baixado diretamente por:

**[⬇️ Download do APK](https://github.com/Miguellbr/ps4-games-databaseFIX/releases/latest/download/app-debug.apk)**

## ⚠️ Observações

O aplicativo precisa de internet para acessar sites externos e abrir links de download. Isso é diferente de depender de um backend da Vercel: a própria aplicação e seus dados locais ficam dentro do APK.

Os links de terceiros podem mudar ou ficar indisponíveis independentemente deste projeto.

## 📄 Licença

Consulte o arquivo [LICENSE](https://github.com/Miguellbr/ps4-games-databaseFIX/blob/main/LICENSE).

---

<div align="center">

**🎮 PS4 Games Database**

[🌐 Página](https://ps4-games-database-fix.vercel.app/) · [📱 APK](https://github.com/Miguellbr/ps4-games-databaseFIX/releases/latest/download/app-debug.apk) · [💻 Código-fonte](https://github.com/Miguellbr/ps4-games-databaseFIX)

</div>
