# Structurizr

`workspace.dsl` is the source of truth for the Puzzle Program C4 model.

It contains:

- system context view
- container view
- orchestrator, camera, solver, and microcontroller component views
- runtime dynamic view for one production cycle
- production deployment view

Generated Structurizr state is ignored by `.gitignore`.



## Start with:

```
docker run --rm -it -p 8080:8080 -v "$($PWD.Path):/usr/local/structurizr" structurizr/structurizr local
```

