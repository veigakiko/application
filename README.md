# Guia Completo de Implantação no Minikube

Este guia fornece instruções detalhadas e passo a passo para criar, configurar, expor e gerenciar um deployment no Minikube usando o `kubectl`. Ele cobre desde a instalação até a solução de problemas comuns.

---

## Pré-requisitos

1. **Instalar o Minikube**:
   Certifique-se de que o Minikube está instalado no seu sistema.
   - [Instruções oficiais de instalação](https://minikube.sigs.k8s.io/docs/start/).

2. **Instalar o Docker**:
   Se você estiver usando o driver Docker, ele deve estar instalado e funcional.
   - [Baixe e instale o Docker](https://www.docker.com/products/docker-desktop).

3. **Instalar o kubectl**:
   O utilitário `kubectl` é necessário para gerenciar o Kubernetes.
   - [Instruções oficiais de instalação](https://kubernetes.io/docs/tasks/tools/).

4. **Verificar virtualização**:
   Certifique-se de que a virtualização está habilitada no BIOS do seu computador, especialmente se você estiver usando drivers como VirtualBox. Isso geralmente é chamado de "Intel VT-x" ou "AMD-V".

5. **Configurar recursos do sistema**:
   Garanta que seu sistema atende aos requisitos mínimos:
   - 2 CPUs.
   - 2 GB de memória livre.
   - 20 GB de espaço em disco.

6. **Verificar rede**:
   Certifique-se de que sua rede permite acesso à internet, pois o Kubernetes pode precisar baixar imagens de contêiner.

---

## Etapas

### Etapa 1: Verificar a Instalação do Minikube
Após instalar o Minikube, verifique se ele foi instalado corretamente:
```bash
minikube version
```
- **Explicação**: Este comando retorna a versão instalada do Minikube. Certifique-se de que a saída é bem-sucedida.

### Etapa 2: Iniciar o Minikube
Inicie o cluster do Minikube.
```bash
minikube start --driver=docker
```
- **Explicação**: Este comando inicia o Minikube usando o driver Docker. Substitua `docker` por outro driver (como `virtualbox` ou `hyperkit`) se necessário.

Opcionalmente, você pode configurar recursos específicos:
```bash
minikube start --cpus=2 --memory=2048 --driver=docker
```
- **Explicação**: Este comando especifica 2 CPUs e 2 GB de memória para o cluster.

---

### Etapa 3: Verificar o Status do Cluster
Certifique-se de que o cluster foi iniciado corretamente:
```bash
minikube status
```
- **Explicação**: Este comando verifica o status do cluster e de seus componentes, como o servidor API e o kubelet.

---

### Etapa 4: Criar um Deployment
Implante um aplicativo no cluster usando uma imagem de contêiner.
```bash
kubectl create deployment hello-minikube --image=kicbase/echo-server:1.0
```
- **Explicação**: Este comando cria um deployment que gerencia pods executando a imagem `kicbase/echo-server:1.0`.

---

### Etapa 5: Expor o Deployment
Crie um serviço para tornar o aplicativo acessível.
```bash
kubectl expose deployment hello-minikube --type=NodePort --port=8080
```
- **Explicação**: Um serviço do tipo `NodePort` permite acesso externo ao aplicativo na porta 8080 do cluster.

---

### Etapa 6: Verificar Recursos
Liste todos os recursos criados no cluster.
```bash
kubectl get all
```
- **Explicação**: Este comando exibe todos os recursos ativos, incluindo pods, serviços e deployments.

---

### Etapa 7: Acessar o Serviço
Use o Minikube para encontrar e acessar o serviço exposto.
```bash
minikube service hello-minikube
```
- **Explicação**: Este comando abre um túnel local para o serviço e fornece uma URL para acessá-lo. Geralmente, ele abre automaticamente no navegador.

---

### Etapa 8: Verificar Logs do Pod (Opcional)
Se houver problemas com o serviço, visualize os logs do pod:
```bash
kubectl logs <nome-do-pod>
```
- **Explicação**: Substitua `<nome-do-pod>` pelo nome do pod, que pode ser obtido com `kubectl get pods`. Os logs ajudam a identificar erros.

---

### Etapa 9: Limpar Recursos
Exclua o deployment e o serviço quando não forem mais necessários:
```bash
kubectl delete deployment hello-minikube
kubectl delete service hello-minikube
```
- **Explicação**: Remove todos os recursos criados no cluster.

---

### Etapa 10: Acessar o Dashboard do Kubernetes (Opcional)
Inicie o Kubernetes Dashboard para gerenciar os recursos visualmente:
```bash
minikube dashboard
```
- **Explicação**: Este comando abre o Dashboard do Kubernetes em seu navegador padrão.

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

## Observações Adicionais

- **Acompanhamento Detalhado**: Use `kubectl describe` para obter mais informações sobre recursos específicos:
```bash
kubectl describe pod <nome-do-pod>
kubectl describe service hello-minikube
kubectl describe deployment hello-minikube
```

- **Configuração Persistente**: Configure o driver padrão para o Minikube:
```bash
minikube config set driver docker
```

---

## Solução de Problemas

1. **Verificar logs do Minikube**:
   ```bash
   minikube logs --file=logs.txt
   ```

2. **Verificar disponibilidade de pods**:
   ```bash
   kubectl get pods
   ```

3. **Recriar recursos**:
   ```bash
   kubectl delete deployment hello-minikube
   kubectl delete service hello-minikube
   ```

4. **Virtualização desabilitada**:
   Certifique-se de que a virtualização está habilitada no BIOS (Intel VT-x ou AMD-V).

5. **Rede e DNS**:
   Teste a conectividade com a internet a partir do pod:
   ```bash
   kubectl exec -it <nome-do-pod> -- ping www.google.com
   ```

Se o problema persistir, consulte a [documentação oficial do Minikube](https://minikube.sigs.k8s.io/docs/) ou abra uma issue no [repositório do Minikube](https://github.com/kubernetes/minikube/issues/new/choose).
