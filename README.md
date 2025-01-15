# Guia de Implantação no Minikube

Este guia fornece instruções detalhadas e passo a passo para criar, expor e gerenciar um deployment no Minikube usando o `kubectl`.

---

## Pré-requisitos

1. O Minikube deve estar instalado no sistema.
2. O Docker deve estar instalado (se você estiver usando o driver Docker).
3. O `kubectl` deve estar instalado e configurado para funcionar com o Minikube.

---

## Etapas

### Etapa 1: Iniciar o Minikube
Inicie o cluster do Minikube.

```bash
minikube start --driver=docker
```

- **Explicação**: Este comando inicia o Minikube usando o driver Docker. Caso prefira outro driver, substitua `docker` pelo driver desejado (como `virtualbox`). Certifique-se de que o driver escolhido está instalado e funcional.

---

### Etapa 2: Verificar o Status do Cluster
Confirme se o cluster do Minikube está em execução.

```bash
minikube status
```

- **Explicação**: Este comando verifica o status dos componentes do Minikube, como o servidor API e o kubelet. O cluster deve estar em execução para seguir as etapas seguintes.

---

### Etapa 3: Criar um Deployment
Implante um aplicativo no cluster.

```bash
kubectl create deployment hello-minikube --image=kicbase/echo-server:1.0
```

- **Explicação**: Este comando cria um deployment que usa a imagem `kicbase/echo-server:1.0`. Um deployment gerencia o estado desejado de seus pods e garante que eles estejam sempre funcionando conforme configurado.

---

### Etapa 4: Expor o Deployment
Exponha o deployment como um serviço para torná-lo acessível.

```bash
kubectl expose deployment hello-minikube --type=NodePort --port=8080
```

- **Explicação**: Este comando cria um serviço do tipo `NodePort`, que permite acessar o deployment através de uma porta específica (neste caso, 8080). O `NodePort` abre uma porta no nó do cluster para acesso externo.

---

### Etapa 5: Verificar Recursos
Liste todos os recursos no cluster para garantir que o deployment e o serviço foram criados corretamente.

```bash
kubectl get all
```

- **Explicação**: Este comando exibe todos os recursos ativos no cluster, incluindo pods, serviços e deployments. Use-o para verificar se tudo está funcionando como esperado.

---

### Etapa 6: Acessar o Serviço
Use o Minikube para encontrar e acessar o serviço.

```bash
minikube service hello-minikube
```

- **Explicação**: Este comando cria um túnel para o serviço e fornece uma URL para acessá-lo localmente. O Minikube geralmente abre automaticamente a URL no navegador padrão.

---

### Etapa 7: Verificar Logs do Pod (Opcional)
Se o serviço não estiver acessível, veja os logs do pod para diagnosticar problemas.

```bash
kubectl logs <nome-do-pod>
```

- **Explicação**: Substitua `<nome-do-pod>` pelo nome real do pod, que pode ser obtido com o comando `kubectl get pods`. Os logs ajudam a identificar erros ou comportamentos inesperados.

---

### Etapa 8: Limpar Recursos
Exclua o deployment e o serviço quando eles não forem mais necessários.

```bash
kubectl delete deployment hello-minikube
kubectl delete service hello-minikube
```

- **Explicação**: Remove o deployment e o serviço do cluster para liberar recursos.

---

### Etapa 9: Acessar o Dashboard do Kubernetes (Opcional)
Inicie o Kubernetes Dashboard para gerenciar os recursos visualmente.

```bash
minikube dashboard
```

- **Explicação**: Este comando abre o Kubernetes Dashboard no navegador, permitindo uma interface gráfica para visualizar e gerenciar os recursos do cluster.

---

## Exemplo Completo de Comandos

```bash
minikube start --driver=docker
minikube status
kubectl create deployment hello-minikube --image=kicbase/echo-server:1.0
kubectl expose deployment hello-minikube --type=NodePort --port=8080
kubectl get all
minikube service hello-minikube
kubectl logs <nome-do-pod>
kubectl delete deployment hello-minikube
kubectl delete service hello-minikube
minikube dashboard
```

---

## Observações

- Substitua `<nome-do-pod>` pelo nome do pod exibido no comando `kubectl get pods`.
- Use `kubectl describe` para obter informações detalhadas sobre os recursos:

```bash
kubectl describe pod <nome-do-pod>
kubectl describe service hello-minikube
kubectl describe deployment hello-minikube
```

---

### Solução de Problemas

Se encontrar problemas:

1. Verifique os logs do Minikube:
   ```bash
   minikube logs --file=logs.txt
   ```

2. Depure pods específicos:
   ```bash
   kubectl logs <nome-do-pod>
   ```

3. Recrie os recursos, se necessário:
   ```bash
   kubectl delete deployment hello-minikube
   kubectl delete service hello-minikube
   ```
