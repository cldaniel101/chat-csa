# React + TypeScript + Vite

Este template oferece uma configuração mínima para rodar React com Vite, incluindo HMR e algumas regras do Oxlint.

Atualmente, dois plugins oficiais estão disponíveis:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) usa [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) usa [SWC](https://swc.rs/)

## React Compiler

O React Compiler não está habilitado neste template por causa do impacto nas performances de dev e build. Para adicioná-lo, veja [esta documentação](https://react.dev/learn/react-compiler/installation).

## Expandindo a configuração do Oxlint

Se você está desenvolvendo uma aplicação de produção, recomendamos habilitar regras de lint cientes de tipos instalando `oxlint-tsgolint` e editando `.oxlintrc.json`:

```json
{
  "$schema": "./node_modules/oxlint/configuration_schema.json",
  "plugins": ["react", "typescript", "oxc"],
  "options": {
    "typeAware": true
  },
  "rules": {
    "react/rules-of-hooks": "error",
    "react/only-export-components": ["warn", { "allowConstantExport": true }]
  }
}
```

Veja a [documentação das regras do Oxlint](https://oxc.rs/docs/guide/usage/linter/rules) para a lista completa de regras e categorias.